# M12 OS Backup Screen - shared UI scale version
import json
import re
import shutil
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup

from utils.logger import log
from utils.ui_scale import (
    title_font,
    button_font,
    text_font,
    status_font,
    row_height,
    button_height,
    padding_size,
    spacing_size,
)


BASE_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = BASE_DIR / "data" / "backups"
GOOGLE_CONFIG_FILE = BASE_DIR / "config" / "google_drive_backup.json"
GOOGLE_BACKUP_FILE = BACKUP_DIR / "google_drive_backup.zip"

BACKUP_ITEMS = [
    BASE_DIR / "config",
    BASE_DIR / "data" / "notes",
    BASE_DIR / "data" / "events",
    BASE_DIR / "data" / "alarms",
]

# Android-safe restore rules.
# These files can be inside protected app/config area on Android.
SKIP_RESTORE_FILES = {
    "config/google_drive_backup.json",
    "config/note_types.json",
}

RESTORE_ALLOWED_PREFIXES = (
    "config/",
    "data/notes/",
    "data/events/",
    "data/alarms/",
)



class BackupScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.selected_backup = None
        self.mode = "backup"
        self.google_status = None
        self.status_label = None
        self.restore_status = None
        self.backup_list = None

        self.build_screen()

    def clear_screen(self):
        self.clear_widgets()

    def make_button(self, text, color=(0.12, 0.20, 0.35, 1)):
        return Button(
            text=text,
            font_size=button_font(),
            background_normal="",
            background_color=color,
        )

    def make_wrapped_label(self, text, font_size, size_hint, bold=False):
        if bold:
            fs = title_font()
        elif font_size >= 20:
            fs = text_font()
        else:
            fs = status_font()

        label = Label(
            text=text,
            font_size=fs,
            bold=bold,
            size_hint=size_hint,
            halign="center",
            valign="middle",
        )
        label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        return label

    def build_screen(self):
        self.clear_screen()
        self.ensure_google_config_file()

        root = BoxLayout(orientation="vertical", padding=padding_size(), spacing=spacing_size())

        root.add_widget(Label(
            text="Backup",
            font_size=title_font(),
            bold=True,
            size_hint=(1, 0.10),
        ))

        tabs = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.10))

        self.backup_tab = self.make_button("Backup")
        self.restore_tab = self.make_button("Restore")
        self.google_tab = self.make_button("Google Drive")

        self.backup_tab.bind(on_press=self.show_backup_tab)
        self.restore_tab.bind(on_press=self.show_restore_tab)
        self.google_tab.bind(on_press=self.show_google_drive_tab)

        tabs.add_widget(self.backup_tab)
        tabs.add_widget(self.restore_tab)
        tabs.add_widget(self.google_tab)
        root.add_widget(tabs)

        self.body = BoxLayout(orientation="vertical", spacing=spacing_size(), size_hint=(1, 0.68))
        root.add_widget(self.body)

        bottom = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.10))

        settings_btn = self.make_button("< Settings", (0.10, 0.15, 0.25, 1))
        settings_btn.bind(on_press=self.go_settings)

        home_btn = self.make_button("< Home", (0.10, 0.15, 0.25, 1))
        home_btn.bind(on_press=self.go_home)

        bottom.add_widget(settings_btn)
        bottom.add_widget(home_btn)
        root.add_widget(bottom)

        self.add_widget(root)
        self.show_backup_tab(None)

    def reset_tabs(self):
        self.backup_tab.background_color = (0.12, 0.20, 0.35, 1)
        self.restore_tab.background_color = (0.12, 0.20, 0.35, 1)
        self.google_tab.background_color = (0.12, 0.20, 0.35, 1)

    def show_backup_tab(self, instance):
        self.mode = "backup"
        self.selected_backup = None
        self.body.clear_widgets()
        self.reset_tabs()
        self.backup_tab.background_color = (0.10, 0.45, 0.20, 1)

        self.body.add_widget(self.make_wrapped_label(
            "Create backup of settings, notes, calendar, and alarms.",
            22,
            (1, 0.22),
        ))

        create_btn = Button(
            text="Create Backup",
            font_size=button_font(),
            size_hint=(1, 0.18),
            background_normal="",
            background_color=(0.10, 0.45, 0.20, 1),
        )
        create_btn.bind(on_press=self.create_backup)
        self.body.add_widget(create_btn)

        self.status_label = self.make_wrapped_label("", 20, (1, 0.40))
        self.body.add_widget(self.status_label)

    def show_restore_tab(self, instance):
        self.mode = "restore"
        self.selected_backup = None
        self.body.clear_widgets()
        self.reset_tabs()
        self.restore_tab.background_color = (0.10, 0.45, 0.20, 1)

        self.restore_status = self.make_wrapped_label("Select backup file.", 20, (1, 0.10))
        self.body.add_widget(self.restore_status)

        scroll = ScrollView(size_hint=(1, 0.43), do_scroll_x=False, do_scroll_y=True)
        self.backup_list = GridLayout(cols=1, spacing=spacing_size(), size_hint_y=None)
        self.backup_list.bind(minimum_height=self.backup_list.setter("height"))
        scroll.add_widget(self.backup_list)
        self.body.add_widget(scroll)

        restore_btn = Button(
            text="Restore Selected",
            font_size=button_font(),
            size_hint=(1, 0.12),
            background_normal="",
            background_color=(0.45, 0.30, 0.10, 1),
        )
        restore_btn.bind(on_press=self.ask_restore_confirmation)
        self.body.add_widget(restore_btn)

        delete_btn = Button(
            text="Delete Selected",
            font_size=button_font(),
            size_hint=(1, 0.12),
            background_normal="",
            background_color=(0.50, 0.15, 0.15, 1),
        )
        delete_btn.bind(on_press=self.ask_delete_confirmation)
        self.body.add_widget(delete_btn)

        self.load_backup_list()

    def show_google_drive_tab(self, instance):
        self.mode = "google_drive"
        self.selected_backup = None
        self.body.clear_widgets()
        self.reset_tabs()
        self.google_tab.background_color = (0.10, 0.45, 0.20, 1)

        self.body.add_widget(self.make_wrapped_label("Google Drive Restore", 28, (1, 0.10), bold=True))

        link = self.load_google_drive_link()
        link_state = "Configured" if link else "Not configured"

        self.body.add_widget(self.make_wrapped_label(
            "Google Drive backup link is read from:\n"
            "config/google_drive_backup.json\n\n"
            f"Current Link: {link_state}",
            19,
            (1, 0.28),
        ))

        download_btn = Button(
            text="Download Backup",
            font_size=button_font(),
            size_hint=(1, 0.16),
            background_normal="",
            background_color=(0.45, 0.30, 0.10, 1),
        )
        download_btn.bind(on_press=self.download_google_drive_backup)
        self.body.add_widget(download_btn)

        clear_btn = Button(
            text="Clear Saved Link",
            font_size=button_font(),
            size_hint=(1, 0.12),
            background_normal="",
            background_color=(0.50, 0.15, 0.15, 1),
        )
        clear_btn.bind(on_press=self.clear_google_drive_link)
        self.body.add_widget(clear_btn)

        self.google_status = self.make_wrapped_label(
            "To set link, edit:\nconfig/google_drive_backup.json",
            18,
            (1, 0.28),
        )
        self.body.add_widget(self.google_status)

    def create_backup(self, instance):
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = BACKUP_DIR / f"m12_backup_{stamp}.zip"

            with zipfile.ZipFile(backup_file, "w", zipfile.ZIP_DEFLATED) as zf:
                for item in BACKUP_ITEMS:
                    if not item.exists():
                        continue
                    if item.is_file():
                        zf.write(item, item.relative_to(BASE_DIR))
                        continue
                    for path in item.rglob("*"):
                        if path.is_file():
                            zf.write(path, path.relative_to(BASE_DIR))

            self.status_label.text = f"Backup Completed\n\n{backup_file.name}"
            log.info(f"Backup created: {backup_file}")

        except Exception as e:
            self.status_label.text = f"Backup failed:\n{e}"
            log.error(f"Backup failed: {e}")

    def load_backup_list(self):
        self.backup_list.clear_widgets()
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        backups = sorted(
            BACKUP_DIR.glob("*.zip"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if not backups:
            self.restore_status.text = "No backups found."
            return

        for backup in backups:
            btn = Button(
                text=backup.name,
                font_size=text_font(),
                size_hint_y=None,
                height=row_height(),
                background_normal="",
                background_color=(0.10, 0.15, 0.25, 1),
                halign="center",
                valign="middle",
            )
            btn.bind(size=lambda inst, val: setattr(inst, "text_size", val))
            btn.bind(on_press=lambda instance, p=backup: self.select_backup(p))
            self.backup_list.add_widget(btn)

    def select_backup(self, backup_path):
        self.selected_backup = backup_path
        self.restore_status.text = f"Selected:\n{backup_path.name}"

    def ask_restore_confirmation(self, instance):
        if not self.selected_backup:
            self.restore_status.text = "Select a backup first."
            return

        box = BoxLayout(orientation="vertical", padding=padding_size(), spacing=spacing_size())
        msg = self.make_wrapped_label(
            "Restore Backup?\n\n"
            f"{self.selected_backup.name}\n\n"
            "Current settings/data will be replaced.\n"
            "Google Drive link will be preserved.",
            22,
            (1, 0.75),
        )
        msg.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - spacing_size(), val[1])))
        box.add_widget(msg)

        buttons = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, None), height=button_height())
        yes_btn = Button(
            text="Yes Restore",
            font_size=button_font(),
            background_normal="",
            background_color=(0.50, 0.15, 0.15, 1),
        )
        no_btn = Button(
            text="No",
            font_size=button_font(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
        )
        buttons.add_widget(yes_btn)
        buttons.add_widget(no_btn)
        box.add_widget(buttons)

        popup = Popup(
            title="Confirm Restore",
            content=box,
            size_hint=(0.90, 0.65),
            auto_dismiss=False,
        )

        def confirm(instance):
            popup.dismiss()
            self.do_restore_selected()

        def cancel(instance):
            popup.dismiss()
            self.restore_status.text = "Restore cancelled."

        yes_btn.bind(on_press=confirm)
        no_btn.bind(on_press=cancel)
        popup.open()

    def do_restore_selected(self):
        """
        Android-safe restore.

        Do NOT use:
        - zipfile.extractall()
        - shutil.rmtree()
        - shutil.copytree()
        - shutil.copy2()

        Android can throw [Errno 1] Operation not permitted for folder deletion,
        metadata copying, or some protected config files. This restore writes
        plain bytes only and skips blocked files instead of crashing.
        """
        restored = 0
        skipped = 0
        failed = 0
        first_error = ""

        try:
            saved_google_link = self.load_google_drive_link()

            if not self.selected_backup or not self.selected_backup.exists():
                self.restore_status.text = "Restore failed:\nBackup file not found."
                return

            with zipfile.ZipFile(self.selected_backup, "r") as zf:
                for info in zf.infolist():
                    name = info.filename.replace("\\", "/").lstrip("/")

                    if not name or name.endswith("/"):
                        skipped += 1
                        continue

                    if name.startswith("__MACOSX/") or "/__MACOSX/" in name:
                        skipped += 1
                        continue

                    # Safety: never allow ZIP paths to escape BASE_DIR.
                    parts = Path(name).parts
                    if ".." in parts:
                        skipped += 1
                        continue

                    if name in SKIP_RESTORE_FILES:
                        skipped += 1
                        log.info(f"Restore skipped protected file: {name}")
                        continue

                    if not name.startswith(RESTORE_ALLOWED_PREFIXES):
                        skipped += 1
                        continue

                    target = BASE_DIR / name

                    try:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        data = zf.read(info)
                        target.write_bytes(data)
                        restored += 1

                    except PermissionError as e:
                        skipped += 1
                        failed += 1
                        if not first_error:
                            first_error = f"{name}: {e}"
                        log.error(f"Restore permission skipped {name}: {e}")
                        continue

                    except OSError as e:
                        skipped += 1
                        failed += 1
                        if not first_error:
                            first_error = f"{name}: {e}"
                        log.error(f"Restore OS error skipped {name}: {e}")
                        continue

            # Preserve the current Google Drive link when possible.
            self.save_google_drive_link(saved_google_link)

            msg = (
                "Restore Complete\n"
                f"Files restored: {restored}\n"
                f"Files skipped: {skipped}\n"
                "Restart M12 OS recommended."
            )

            if failed:
                msg += (
                    "\n\nSome Android-protected files were skipped.\n"
                    f"First skipped error:\n{first_error}"
                )

            self.restore_status.text = msg

            self.refresh_after_restore()
            log.info(
                f"Backup restored: {self.selected_backup} "
                f"restored={restored} skipped={skipped} failed={failed}"
            )

        except Exception as e:
            self.restore_status.text = f"Restore failed:\n{type(e).__name__}\n{e}"
            log.error(f"Restore failed: {type(e).__name__}: {e}")

    def restore_config_folder(self, restore_tmp, saved_google_link):
        """
        Kept for compatibility with older code paths.
        New restore does not call this method.
        """
        return

    def restore_data_folder(self, restore_tmp, folder_name):
        """
        Kept for compatibility with older code paths.
        New restore does not call this method.
        """
        return

    def refresh_after_restore(self):
        try:
            if self.manager and self.manager.has_screen("calendar"):
                cal = self.manager.get_screen("calendar")

                if hasattr(cal, "load_events") and hasattr(cal, "normalize_event"):
                    cal.events = [cal.normalize_event(e) for e in cal.load_events()]

                    if hasattr(cal, "sort_events"):
                        cal.sort_events()

                    cal.selected_index = None

                    if hasattr(cal, "build_list_view"):
                        cal.build_list_view()

            if self.manager and self.manager.has_screen("home"):
                home = self.manager.get_screen("home")

                if hasattr(home, "refresh_calendar_button"):
                    home.refresh_calendar_button()

                if hasattr(home, "refresh_clock_button"):
                    home.refresh_clock_button()

        except Exception as e:
            log.error(f"Backup restore refresh failed: {e}")

    def ask_delete_confirmation(self, instance):
        if not self.selected_backup:
            self.restore_status.text = "Select a backup first."
            return

        box = BoxLayout(orientation="vertical", padding=padding_size(), spacing=spacing_size())
        msg = self.make_wrapped_label(
            "Delete Backup?\n\n"
            f"{self.selected_backup.name}\n\n"
            "This cannot be undone.",
            22,
            (1, 0.75),
        )
        msg.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - spacing_size(), val[1])))
        box.add_widget(msg)

        buttons = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, None), height=button_height())
        delete_btn = Button(
            text="Delete",
            font_size=button_font(),
            background_normal="",
            background_color=(0.50, 0.15, 0.15, 1),
        )
        cancel_btn = Button(
            text="Cancel",
            font_size=button_font(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
        )
        buttons.add_widget(delete_btn)
        buttons.add_widget(cancel_btn)
        box.add_widget(buttons)

        popup = Popup(
            title="Confirm Delete",
            content=box,
            size_hint=(0.90, 0.65),
            auto_dismiss=False,
        )

        def confirm_delete(instance):
            popup.dismiss()
            self.delete_selected_backup()

        def cancel_delete(instance):
            popup.dismiss()
            self.restore_status.text = "Delete cancelled."

        delete_btn.bind(on_press=confirm_delete)
        cancel_btn.bind(on_press=cancel_delete)
        popup.open()

    def delete_selected_backup(self):
        try:
            if not self.selected_backup:
                self.restore_status.text = "Select a backup first."
                return

            backup_path = self.selected_backup
            backup_name = backup_path.name

            if backup_path.exists():
                backup_path.unlink()

            self.selected_backup = None
            self.restore_status.text = f"Deleted:\n{backup_name}"
            self.load_backup_list()
            log.info(f"Backup deleted: {backup_name}")

        except Exception as e:
            self.restore_status.text = f"Delete failed:\n{e}"
            log.error(f"Backup delete failed: {e}")

    def ensure_google_config_file(self):
        try:
            GOOGLE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

            if not GOOGLE_CONFIG_FILE.exists():
                GOOGLE_CONFIG_FILE.write_text(
                    json.dumps({"backup_link": ""}, indent=4),
                    encoding="utf-8",
                )
                log.info(f"Google Drive config created: {GOOGLE_CONFIG_FILE}")

        except Exception as e:
            log.error(f"Google Drive config create failed: {e}")

    def load_google_drive_link(self):
        try:
            self.ensure_google_config_file()
            data = json.loads(GOOGLE_CONFIG_FILE.read_text(encoding="utf-8"))

            if isinstance(data, dict):
                return str(data.get("backup_link", "")).strip()

        except Exception as e:
            log.error(f"Google Drive link load failed: {e}")

        return ""

    def save_google_drive_link(self, link):
        try:
            GOOGLE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            GOOGLE_CONFIG_FILE.write_text(
                json.dumps({"backup_link": link.strip()}, indent=4),
                encoding="utf-8",
            )
            log.info("Google Drive backup link saved")
            return True

        except Exception as e:
            log.error(f"Google Drive link save failed: {e}")
            return False

    def clear_google_drive_link(self, instance):
        try:
            self.save_google_drive_link("")
            if self.google_status:
                self.google_status.text = (
                    "Link cleared.\n"
                    "Edit config/google_drive_backup.json to set new link."
                )
            self.show_google_drive_tab(None)

        except Exception as e:
            if self.google_status:
                self.google_status.text = f"Clear failed:\n{e}"

    def extract_google_drive_file_id(self, link):
        link = link.strip()

        if not link:
            return ""

        match = re.search(r"/file/d/([^/]+)", link)
        if match:
            return match.group(1)

        parsed = urlparse(link)
        query = parse_qs(parsed.query)

        if "id" in query and query["id"]:
            return query["id"][0]

        return ""

    def google_drive_direct_url(self, link):
        file_id = self.extract_google_drive_file_id(link)

        if not file_id:
            return ""

        return f"https://drive.google.com/uc?export=download&id={file_id}"

    def download_google_drive_backup(self, instance):
        link = self.load_google_drive_link()

        if not link:
            self.google_status.text = (
                "No Google Drive link configured.\n\n"
                "Edit this file:\n"
                "config/google_drive_backup.json"
            )
            return

        direct_url = self.google_drive_direct_url(link)

        if not direct_url:
            self.google_status.text = "Invalid Google Drive link in config file."
            return

        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            temp_file = BACKUP_DIR / "google_drive_backup_download.tmp"
            final_file = GOOGLE_BACKUP_FILE

            self.google_status.text = "Downloading..."

            req = urllib.request.Request(
                direct_url,
                headers={"User-Agent": "Mozilla/5.0"},
            )

            with urllib.request.urlopen(req, timeout=45) as response:
                data = response.read()

            temp_file.write_bytes(data)

            if not zipfile.is_zipfile(temp_file):
                temp_file.unlink(missing_ok=True)
                self.google_status.text = (
                    "Downloaded file is not a ZIP.\n"
                    "Make sure Google Drive sharing is set to Anyone with the link."
                )
                return

            if final_file.exists():
                final_file.unlink()

            temp_file.rename(final_file)

            self.google_status.text = (
                "Download Complete\n\n"
                "google_drive_backup.zip\n\n"
                "Opening Restore tab..."
            )

            log.info(f"Google Drive backup downloaded: {final_file}")
            self.show_restore_tab(None)

        except Exception as e:
            self.google_status.text = f"Download failed:\n{e}"
            log.error(f"Google Drive backup download failed: {e}")

    def go_settings(self, instance):
        if self.manager:
            self.manager.current = "settings"

    def go_home(self, instance):
        if self.manager:
            self.manager.current = "home"
