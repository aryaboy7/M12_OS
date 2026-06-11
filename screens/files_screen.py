from pathlib import Path
from datetime import datetime
import os
import shutil

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput

from utils.ui_scale import font
from utils.logger import log


class FileRow(BoxLayout):
    def __init__(self, path, is_folder, on_open_callback, on_check_callback, is_checked=False, **kwargs):
        # M12 / narrow screen uses readable 2-line layout.
        # Mac / tablet uses compact columns.
        if Window.width < 700:
            super().__init__(
                orientation="horizontal",
                spacing=6,
                size_hint_y=None,
                height=76,
                **kwargs
            )
        else:
            super().__init__(
                orientation="horizontal",
                spacing=4,
                size_hint_y=None,
                height=60,
                **kwargs
            )

        self.path = Path(path)
        self.is_folder = is_folder
        self.on_open_callback = on_open_callback
        self.on_check_callback = on_check_callback
        self.is_checked = is_checked

        if Window.width < 700:
            self.build_m12_row()
        else:
            self.build_column_row()

    def build_m12_row(self):
        check_bg = (0.12, 0.20, 0.35, 1)
        bg = (0.10, 0.15, 0.25, 1)

        check_btn = Button(
            text="[X]" if self.is_checked else "[ ]",
            font_size=font(20),
            size_hint=(0.16, 1),
            halign="center",
            valign="middle",
            background_normal="",
            background_color=check_bg
        )
        check_btn.bind(on_release=self.check_pressed)
        self.add_widget(check_btn)

        icon = "[D]" if self.is_folder else "[F]"
        name = self.path.name or str(self.path)

        if len(name) > 32:
            name = name[:29] + "..."

        type_text = "DIR" if self.is_folder else self.extension_text()
        size_text = "" if self.is_folder else self.size_text()
        date_text = self.date_text()
        rw_text = self.permission_text()

        line1 = f"{icon} {name}"

        parts = [type_text]
        if size_text:
            parts.append(size_text)
        if date_text:
            parts.append(date_text)
        if rw_text:
            parts.append(rw_text)

        line2 = " | ".join(parts)

        main_btn = Button(
            text=f"{line1}\n{line2}",
            font_size=font(17),
            size_hint=(0.84, 1),
            halign="left",
            valign="middle",
            background_normal="",
            background_color=bg
        )
        main_btn.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - 12, val[1])))
        main_btn.bind(on_release=self.open_pressed)
        self.add_widget(main_btn)

    def build_column_row(self):
        bg = (0.10, 0.15, 0.25, 1)
        check_bg = (0.12, 0.20, 0.35, 1)
        fs = font(14)

        icon = "[D]" if self.is_folder else "[F]"
        name = self.path.name or str(self.path)

        if len(name) > self.name_limit():
            name = name[:self.name_limit() - 3] + "..."

        type_text = "DIR" if self.is_folder else self.extension_text()
        size_text = "" if self.is_folder else self.size_text()
        date_text = self.date_text()
        rw_text = self.permission_text()

        cols = [
            ("[X]" if self.is_checked else "[ ]", 0.08, check_bg, "check"),
            (f"{icon} {name}", 0.36, bg, "open"),
            (type_text, 0.11, bg, "open"),
            (size_text, 0.13, bg, "open"),
            (date_text, 0.22, bg, "open"),
            (rw_text, 0.10, bg, "open"),
        ]

        for text, width, color, action in cols:
            btn = Button(
                text=text,
                font_size=fs,
                size_hint=(width, 1),
                halign="left" if action == "open" else "center",
                valign="middle",
                background_normal="",
                background_color=color
            )
            btn.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - 6, val[1])))

            if action == "check":
                btn.bind(on_release=self.check_pressed)
            else:
                btn.bind(on_release=self.open_pressed)

            self.add_widget(btn)

    def check_pressed(self, instance):
        self.on_check_callback(self.path)

    def open_pressed(self, instance):
        self.on_open_callback(self.path, self.is_folder)

    def name_limit(self):
        return 32

    def extension_text(self):
        suffix = self.path.suffix.lower().replace(".", "")
        return suffix.upper() if suffix else "-"

    def size_text(self):
        try:
            size = self.path.stat().st_size
            if size < 1024:
                return f"{size}B"
            if size < 1024 * 1024:
                return f"{size / 1024:.1f}K"
            if size < 1024 * 1024 * 1024:
                return f"{size / (1024 * 1024):.1f}M"
            return f"{size / (1024 * 1024 * 1024):.1f}G"
        except Exception:
            return ""

    def date_text(self):
        try:
            dt = datetime.fromtimestamp(self.path.stat().st_mtime)
            if Window.width < 700:
                return dt.strftime("%m/%d %H:%M")
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return ""

    def permission_text(self):
        try:
            r = os.access(self.path, os.R_OK)
            w = os.access(self.path, os.W_OK)
            if r and w:
                return "RW"
            if r:
                return "R"
            if w:
                return "W"
            return "-"
        except Exception:
            return "-"


class FilesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.current_path = self.default_start_path()
        self.checked_paths = set()
        self.current_visible_paths = []
        self.pending_delete_checked = False

        self.clipboard_paths = []
        self.clipboard_mode = ""  # "copy" or "cut"

        self.input_mode = None
        self.rename_target = None

        self.root_box = BoxLayout(orientation="vertical", padding=8, spacing=6)
        self.add_widget(self.root_box)

        self.build_main_view()

    def build_main_view(self):
        self.root_box.clear_widgets()

        title = Label(
            text="File Manager",
            font_size=font(26),
            bold=True,
            size_hint=(1, 0.06)
        )
        self.root_box.add_widget(title)

        self.path_label = Label(
            text="Path",
            font_size=font(14),
            size_hint=(1, 0.065),
            halign="left",
            valign="middle"
        )
        self.path_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.root_box.add_widget(self.path_label)

        top_buttons = BoxLayout(orientation="horizontal", spacing=5, size_hint=(1, 0.075))

        parent_btn = self.make_btn("< Parent")
        parent_btn.bind(on_release=self.go_parent)
        top_buttons.add_widget(parent_btn)

        home_btn = self.make_btn("Home")
        home_btn.bind(on_release=self.go_start)
        top_buttons.add_widget(home_btn)

        refresh_btn = self.make_btn("Refresh")
        refresh_btn.bind(on_release=self.refresh)
        top_buttons.add_widget(refresh_btn)

        self.root_box.add_widget(top_buttons)

        actions1 = BoxLayout(orientation="horizontal", spacing=5, size_hint=(1, 0.075))

        new_folder_btn = self.make_btn("New Folder")
        new_folder_btn.bind(on_release=self.show_new_folder_input)
        actions1.add_widget(new_folder_btn)

        new_file_btn = self.make_btn("New File")
        new_file_btn.bind(on_release=self.show_new_file_input)
        actions1.add_widget(new_file_btn)

        rename_btn = self.make_btn("Rename")
        rename_btn.bind(on_release=self.show_rename_input)
        actions1.add_widget(rename_btn)

        self.root_box.add_widget(actions1)

        actions2 = BoxLayout(orientation="horizontal", spacing=5, size_hint=(1, 0.075))

        copy_btn = self.make_btn("Copy")
        copy_btn.bind(on_release=self.copy_checked)
        actions2.add_widget(copy_btn)

        cut_btn = self.make_btn("Cut")
        cut_btn.bind(on_release=self.cut_checked)
        actions2.add_widget(cut_btn)

        paste_btn = self.make_btn("Paste")
        paste_btn.bind(on_release=self.paste_clipboard)
        actions2.add_widget(paste_btn)

        self.root_box.add_widget(actions2)

        self.status_label = Label(
            text="",
            font_size=font(13),
            size_hint=(1, 0.055),
            halign="left",
            valign="middle"
        )
        self.status_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.root_box.add_widget(self.status_label)

        header = BoxLayout(orientation="horizontal", spacing=4, size_hint=(1, 0.045))

        if Window.width < 700:
            header_cols = [
                ("Sel", 0.16),
                ("File / Info", 0.84),
            ]
        else:
            header_cols = [
                ("Sel", 0.08),
                ("Name", 0.36),
                ("Type", 0.11),
                ("Size", 0.13),
                ("Modified", 0.22),
                ("RW", 0.10),
            ]

        for text, width in header_cols:
            if text == "Sel":
                sel_btn = Button(
                    text="[b][u]Sel[/u][/b]",
                    markup=True,
                    font_size=font(13),
                    size_hint=(width, 1),
                    background_normal="",
                    background_color=(0.12, 0.20, 0.35, 1)
                )
                sel_btn.bind(on_release=self.toggle_select_all_visible)
                header.add_widget(sel_btn)
            else:
                header.add_widget(Label(
                    text=text,
                    font_size=font(13),
                    bold=True,
                    size_hint=(width, 1),
                    halign="left",
                    valign="middle"
                ))

        self.root_box.add_widget(header)

        self.scroll = ScrollView(size_hint=(1, 0.475), do_scroll_x=False, do_scroll_y=True)

        self.file_list = GridLayout(cols=1, spacing=4, size_hint_y=None)
        self.file_list.bind(minimum_height=self.file_list.setter("height"))

        self.scroll.add_widget(self.file_list)
        self.root_box.add_widget(self.scroll)

        bottom = BoxLayout(orientation="horizontal", spacing=5, size_hint=(1, 0.075))

        clear_btn = self.make_btn("Clear")
        clear_btn.bind(on_release=self.clear_checked)
        bottom.add_widget(clear_btn)

        delete_btn = Button(
            text="Delete Checked",
            font_size=font(15 if Window.width < 700 else 17),
            background_normal="",
            background_color=(0.35, 0.12, 0.12, 1)
        )
        delete_btn.bind(on_release=self.delete_checked_confirm)
        bottom.add_widget(delete_btn)

        back_btn = self.make_btn("< Back")
        back_btn.bind(on_release=self.go_back)
        bottom.add_widget(back_btn)

        self.root_box.add_widget(bottom)

    def make_btn(self, text):
        return Button(
            text=text,
            font_size=font(15 if Window.width < 700 else 17),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )

    def build_input_view(self, title, default_text, ok_callback):
        self.root_box.clear_widgets()

        self.root_box.add_widget(Label(
            text=title,
            font_size=font(28),
            bold=True,
            size_hint=(1, 0.14)
        ))

        self.input_status = Label(
            text=f"Current folder:\n{self.short_path(self.current_path)}",
            font_size=font(14),
            size_hint=(1, 0.18),
            halign="center",
            valign="middle"
        )
        self.input_status.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.root_box.add_widget(self.input_status)

        self.name_input = TextInput(
            text=default_text,
            multiline=False,
            font_size=font(22),
            size_hint=(1, 0.14),
            background_color=(1, 1, 1, 1),
            foreground_color=(0, 0, 0, 1)
        )
        self.root_box.add_widget(self.name_input)

        buttons = BoxLayout(orientation="horizontal", spacing=8, size_hint=(1, 0.14))

        ok_btn = Button(
            text="OK",
            font_size=font(22),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        ok_btn.bind(on_release=ok_callback)
        buttons.add_widget(ok_btn)

        cancel_btn = Button(
            text="Cancel",
            font_size=font(22),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        cancel_btn.bind(on_release=self.cancel_input)
        buttons.add_widget(cancel_btn)

        self.root_box.add_widget(buttons)

        self.root_box.add_widget(Label(
            text="",
            size_hint=(1, 0.40)
        ))

        Clock.schedule_once(lambda dt: self.name_input.focus == True, 0.2)

    def default_start_path(self):
        if platform == "android":
            p = Path("/storage/emulated/0")
            if p.exists():
                return p
        return Path.home()

    def on_enter(self):
        log.info("Files: opened")
        self.pending_delete_checked = False
        Clock.schedule_once(lambda dt: self.load_path(self.current_path), 0.05)

    def short_path(self, path):
        text = str(path)
        if len(text) <= 70:
            return text
        return "..." + text[-67:]

    def load_path(self, path):
        try:
            path = Path(path)

            if not path.exists():
                self.status_label.text = "Path does not exist."
                path = self.default_start_path()

            if not path.is_dir():
                path = path.parent

            self.current_path = path
            self.pending_delete_checked = False
            self.checked_paths = {p for p in self.checked_paths if p.exists()}

            self.path_label.text = f"Path: {self.short_path(path)}"
            self.file_list.clear_widgets()

            try:
                items = [item for item in path.iterdir() if not item.name.startswith(".")]
            except PermissionError:
                self.status_label.text = "Permission denied."
                return
            except Exception as e:
                self.status_label.text = f"Read error: {e}"
                return

            folders = sorted([x for x in items if x.is_dir()], key=lambda p: p.name.lower())
            files = sorted([x for x in items if x.is_file()], key=lambda p: p.name.lower())

            self.current_visible_paths = folders + files

            for folder in folders:
                self.file_list.add_widget(
                    FileRow(folder, True, self.item_pressed, self.toggle_checked, folder in self.checked_paths)
                )

            for file_path in files:
                self.file_list.add_widget(
                    FileRow(file_path, False, self.item_pressed, self.toggle_checked, file_path in self.checked_paths)
                )

            self.update_status(f"{len(folders)} folders, {len(files)} files")
            self.scroll.scroll_y = 1

        except Exception as e:
            self.status_label.text = f"File Manager error: {e}"
            log.error(f"Files error: {e}")

    def update_status(self, prefix=None):
        checked = len(self.checked_paths)
        clip = ""
        if self.clipboard_paths:
            clip = f" | {self.clipboard_mode.upper()}: {len(self.clipboard_paths)}"
        if prefix:
            self.status_label.text = f"{prefix} | Checked: {checked}{clip}"
        else:
            self.status_label.text = f"Checked: {checked}{clip}"

    def item_pressed(self, path, is_folder):
        path = Path(path)

        if is_folder:
            self.load_path(path)
            return

        self.status_label.text = f"File: {path.name} | Check box for actions."

    def toggle_checked(self, path):
        path = Path(path)

        if path in self.checked_paths:
            self.checked_paths.remove(path)
        else:
            self.checked_paths.add(path)

        self.pending_delete_checked = False

        old_scroll = self.scroll.scroll_y
        self.load_path(self.current_path)
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", old_scroll), 0)

    def toggle_select_all_visible(self, instance):
        if not self.current_visible_paths:
            self.status_label.text = "Nothing to select."
            return

        visible_set = set(self.current_visible_paths)
        old_scroll = self.scroll.scroll_y

        if visible_set.issubset(self.checked_paths):
            self.checked_paths -= visible_set
            self.pending_delete_checked = False
            self.load_path(self.current_path)
            Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", old_scroll), 0)
            self.status_label.text = "Visible items unchecked."
            return

        self.checked_paths |= visible_set
        self.pending_delete_checked = False
        self.load_path(self.current_path)
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", old_scroll), 0)
        self.status_label.text = f"Selected all visible: {len(visible_set)}"

    def clear_checked(self, instance):
        self.checked_paths.clear()
        self.pending_delete_checked = False
        self.load_path(self.current_path)

    def go_parent(self, instance):
        parent = self.current_path.parent
        if parent and parent != self.current_path:
            self.load_path(parent)

    def go_start(self, instance):
        self.load_path(self.default_start_path())

    def refresh(self, instance):
        self.load_path(self.current_path)

    def go_back(self, instance):
        log.info("Files: Back pressed")
        self.manager.current = "home"

    def show_new_folder_input(self, instance):
        self.input_mode = "new_folder"
        self.build_input_view("Create Folder", "New Folder", self.create_folder)

    def show_new_file_input(self, instance):
        self.input_mode = "new_file"
        self.build_input_view("Create Empty File", "new_file.txt", self.create_file)

    def show_rename_input(self, instance):
        if len(self.checked_paths) != 1:
            self.status_label.text = "Check exactly one item to rename."
            return

        self.rename_target = next(iter(self.checked_paths))
        self.input_mode = "rename"
        self.build_input_view("Rename", self.rename_target.name, self.rename_item)

    def cancel_input(self, instance):
        self.input_mode = None
        self.rename_target = None
        self.build_main_view()
        self.load_path(self.current_path)

    def clean_name(self, name):
        name = str(name).strip()

        if not name:
            return ""

        bad = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]
        for ch in bad:
            name = name.replace(ch, "_")

        return name

    def unique_path(self, path):
        path = Path(path)

        if not path.exists():
            return path

        parent = path.parent
        stem = path.stem
        suffix = path.suffix

        for i in range(1, 1000):
            candidate = parent / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                return candidate

        return parent / f"{stem}_copy{suffix}"

    def create_folder(self, instance):
        name = self.clean_name(self.name_input.text)

        if not name:
            self.input_status.text = "Folder name is empty."
            return

        target = self.unique_path(self.current_path / name)

        try:
            target.mkdir(parents=False, exist_ok=False)
            log.info(f"Files: folder created {target}")
            self.cancel_input(None)
            self.status_label.text = f"Folder created: {target.name}"
        except Exception as e:
            self.input_status.text = f"Create folder failed:\n{e}"

    def create_file(self, instance):
        name = self.clean_name(self.name_input.text)

        if not name:
            self.input_status.text = "File name is empty."
            return

        target = self.unique_path(self.current_path / name)

        try:
            target.write_text("", encoding="utf-8")
            log.info(f"Files: file created {target}")
            self.cancel_input(None)
            self.status_label.text = f"File created: {target.name}"
        except Exception as e:
            self.input_status.text = f"Create file failed:\n{e}"

    def rename_item(self, instance):
        if not self.rename_target:
            self.input_status.text = "No item selected."
            return

        new_name = self.clean_name(self.name_input.text)

        if not new_name:
            self.input_status.text = "Name is empty."
            return

        target = self.rename_target
        new_path = self.unique_path(target.parent / new_name)

        try:
            target.rename(new_path)
            log.info(f"Files: renamed {target} -> {new_path}")
            self.checked_paths.clear()
            self.rename_target = None
            self.cancel_input(None)
            self.status_label.text = f"Renamed: {new_path.name}"
        except Exception as e:
            self.input_status.text = f"Rename failed:\n{e}"

    def copy_checked(self, instance):
        if not self.checked_paths:
            self.status_label.text = "Check item(s) to copy."
            return

        self.clipboard_paths = list(self.checked_paths)
        self.clipboard_mode = "copy"
        self.status_label.text = f"Copy ready: {len(self.clipboard_paths)} item(s). Go to folder and press Paste."

    def cut_checked(self, instance):
        if not self.checked_paths:
            self.status_label.text = "Check item(s) to cut."
            return

        self.clipboard_paths = list(self.checked_paths)
        self.clipboard_mode = "cut"
        self.status_label.text = f"Cut ready: {len(self.clipboard_paths)} item(s). Go to folder and press Paste."

    def paste_clipboard(self, instance):
        if not self.clipboard_paths or self.clipboard_mode not in ("copy", "cut"):
            self.status_label.text = "Nothing to paste."
            return

        copied = 0
        failed = 0

        for src in list(self.clipboard_paths):
            try:
                src = Path(src)

                if not src.exists():
                    failed += 1
                    continue

                dst = self.unique_path(self.current_path / src.name)

                if self.clipboard_mode == "copy":
                    if src.is_dir():
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)

                elif self.clipboard_mode == "cut":
                    shutil.move(str(src), str(dst))

                copied += 1

            except Exception as e:
                failed += 1
                log.error(f"Paste failed {src}: {e}")

        if self.clipboard_mode == "cut":
            self.clipboard_paths = []
            self.clipboard_mode = ""

        self.checked_paths.clear()
        self.load_path(self.current_path)
        self.status_label.text = f"Pasted: {copied} | Failed: {failed}"

    def delete_checked_confirm(self, instance):
        if not self.checked_paths:
            self.status_label.text = "No checked files or folders."
            return

        if not self.pending_delete_checked:
            self.pending_delete_checked = True
            self.status_label.text = f"Press Delete Checked again to delete {len(self.checked_paths)} item(s)."
            return

        self.delete_checked_now()

    def delete_checked_now(self):
        deleted = 0
        failed = 0

        targets = sorted(list(self.checked_paths), key=lambda p: len(p.parts), reverse=True)

        for target in targets:
            try:
                if not target.exists():
                    deleted += 1
                    continue

                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()

                deleted += 1

            except Exception as e:
                failed += 1
                log.error(f"Delete failed {target}: {e}")

        self.checked_paths.clear()
        self.pending_delete_checked = False
        self.load_path(self.current_path)
        self.status_label.text = f"Deleted: {deleted} | Failed: {failed}"
