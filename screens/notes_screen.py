import json
from pathlib import Path

from kivy.core.window import Window
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout

from utils.logger import log


BASE_DIR = Path(__file__).resolve().parent.parent
NOTES_DIR = BASE_DIR / "data" / "notes"
TYPES_FILE = BASE_DIR / "config" / "note_types.json"
NOTES_DIR.mkdir(parents=True, exist_ok=True)


def device_profile():
    w = Window.width
    h = Window.height

    if h >= 1800:
        return "phone"

    if w < 700 and h >= 900:
        return "m12"

    if h >= 1100:
        return "tablet"

    return "desktop"


def is_mobile():
    return device_profile() in ("phone", "tablet", "m12")


def notes_font(base):
    profile = device_profile()

    if profile == "phone":
        scale = 1.85
    elif profile == "tablet":
        scale = 1.45
    elif profile == "m12":
        scale = 1.30
    else:
        scale = 1.00

    return max(14, int(base * scale))


def row_height():
    profile = device_profile()

    if profile == "phone":
        return 150
    if profile == "tablet":
        return 118
    if profile == "m12":
        return 92

    return 80


class NotesScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.selected_note = None
        self.current_filter = "All"

        profile = device_profile()

        if profile == "phone":
            padding = 22
            spacing = 14
            title_hint = 0.08
            filter_hint = 0.17
            list_hint = 0.61
            bottom_hint = 0.14
        elif profile == "tablet":
            padding = 16
            spacing = 10
            title_hint = 0.08
            filter_hint = 0.17
            list_hint = 0.60
            bottom_hint = 0.15
        elif profile == "m12":
            padding = 10
            spacing = 8
            title_hint = 0.08
            filter_hint = 0.16
            list_hint = 0.61
            bottom_hint = 0.15
        else:
            padding = 10
            spacing = 8
            title_hint = 0.10
            filter_hint = 0.18
            list_hint = 0.57
            bottom_hint = 0.15

        layout = BoxLayout(
            orientation="vertical",
            spacing=spacing,
            padding=padding
        )

        title = Label(
            text="Notes",
            font_size=notes_font(32),
            bold=True,
            size_hint=(1, title_hint)
        )
        layout.add_widget(title)

        self.filter_box = GridLayout(
            cols=self.filter_cols(),
            spacing=6,
            size_hint=(1, filter_hint)
        )
        layout.add_widget(self.filter_box)

        scroll = ScrollView(
            size_hint=(1, list_hint),
            do_scroll_x=False,
            do_scroll_y=True
        )

        self.notes_box = GridLayout(
            cols=1,
            spacing=8 if is_mobile() else 6,
            size_hint_y=None
        )
        self.notes_box.bind(minimum_height=self.notes_box.setter("height"))

        scroll.add_widget(self.notes_box)
        layout.add_widget(scroll)

        bottom = GridLayout(
            cols=5 if not is_mobile() else 3,
            spacing=8,
            size_hint=(1, bottom_hint)
        )

        for text, callback in [
            ("New", self.new_note),
            ("Open", self.open_note),
            ("Delete", self.delete_note),
            ("Types", self.open_types),
            ("Back", self.go_back),
        ]:
            btn = Button(
                text=text,
                font_size=notes_font(17 if is_mobile() else 18),
                background_normal="",
                background_color=(0.10, 0.15, 0.25, 1)
            )
            btn.bind(on_press=callback)
            bottom.add_widget(btn)

        layout.add_widget(bottom)
        self.add_widget(layout)

    def filter_cols(self):
        profile = device_profile()

        if profile == "phone":
            return 2

        if profile in ("tablet", "m12"):
            return 3

        return 3

    def on_enter(self):
        self.refresh_filters()
        self.refresh_notes()

    def load_types(self):
        try:
            if TYPES_FILE.exists():
                data = json.loads(TYPES_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
        except Exception as e:
            log.error(f"Notes: failed to load types: {e}")

        return ["Personal", "Work", "Project", "Shopping", "Idea"]

    def read_note_data(self, path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "title": data.get("title", path.stem),
                "type": data.get("type", "Personal"),
                "body": data.get("body", "")
            }
        except Exception:
            try:
                return {
                    "title": path.stem,
                    "type": "Personal",
                    "body": path.read_text(encoding="utf-8")
                }
            except Exception:
                return {
                    "title": path.stem,
                    "type": "Personal",
                    "body": ""
                }

    def refresh_filters(self):
        self.filter_box.clear_widgets()

        filters = ["All"] + self.load_types()
        self.filter_box.cols = self.filter_cols()

        for name in filters:
            color = (
                (0.25, 0.45, 0.75, 1)
                if name == self.current_filter
                else (0.12, 0.20, 0.35, 1)
            )

            btn = Button(
                text=name,
                font_size=notes_font(15 if is_mobile() else 18),
                background_normal="",
                background_color=color
            )
            btn.bind(on_press=lambda instance, f=name: self.set_filter(f))
            self.filter_box.add_widget(btn)

    def set_filter(self, note_type):
        self.current_filter = note_type
        self.selected_note = None
        log.info(f"Notes: filter {note_type}")
        self.refresh_filters()
        self.refresh_notes()

    def refresh_notes(self):
        self.notes_box.clear_widgets()

        files = sorted(
            list(NOTES_DIR.glob("*.json")) + list(NOTES_DIR.glob("*.txt")),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        visible_files = []

        for file in files:
            data = self.read_note_data(file)
            if self.current_filter == "All" or data["type"] == self.current_filter:
                visible_files.append((file, data))

        if not visible_files:
            self.notes_box.add_widget(
                Label(
                    text="No notes found",
                    font_size=notes_font(22),
                    size_hint_y=None,
                    height=row_height()
                )
            )
            return

        for file, data in visible_files:
            title = str(data["title"]).strip() or file.stem
            note_type = str(data["type"]).strip() or "Personal"
            preview = data["body"].replace("\n", " ").strip()

            if is_mobile():
                if len(title) > 30:
                    title = title[:27] + "..."

                # On mobile, keep it readable: title + type only.
                text = f"{title}\n{note_type}"
                fs = notes_font(18)
            else:
                if len(preview) > 60:
                    preview = preview[:60] + "..."

                text = f"{title}\n{note_type} | {preview}"
                fs = notes_font(18)

            btn = Button(
                text=text,
                font_size=fs,
                size_hint_y=None,
                height=row_height(),
                background_normal="",
                background_color=(0.12, 0.20, 0.35, 1),
                halign="left",
                valign="middle"
            )
            btn.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - 20, val[1])))

            if self.selected_note == file:
                btn.background_color = (0.25, 0.45, 0.75, 1)

            btn.bind(on_press=lambda instance, p=file: self.select_note(p))
            self.notes_box.add_widget(btn)

    def select_note(self, path):
        self.selected_note = path
        log.info(f"Notes: selected {path.name}")
        self.refresh_notes()

    def new_note(self, instance):
        log.info("Notes: New pressed")
        editor = self.manager.get_screen("editor")
        editor.new_note()
        self.manager.current = "editor"

    def open_note(self, instance):
        if not self.selected_note:
            log.warning("Notes: Open pressed with no selection")
            return

        editor = self.manager.get_screen("editor")
        editor.load_note(self.selected_note)

        log.info(f"Notes: opening {self.selected_note.name}")
        self.manager.current = "editor"

    def delete_note(self, instance):
        if not self.selected_note:
            log.warning("Notes: Delete pressed with no selection")
            return

        if self.selected_note.exists():
            log.info(f"Notes: deleted {self.selected_note.name}")
            self.selected_note.unlink()

        self.selected_note = None
        self.refresh_notes()

    def open_types(self, instance):
        log.info("Notes: Types pressed")
        self.manager.current = "note_types"

    def go_back(self, instance):
        log.info("Notes: Back pressed")
        self.manager.current = "home"
