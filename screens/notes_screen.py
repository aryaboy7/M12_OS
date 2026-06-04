import json
from pathlib import Path

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


class NotesScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_note = None
        self.current_filter = "All"

        layout = BoxLayout(orientation="vertical", spacing=8, padding=10)

        title = Label(text="Notes", font_size=32, size_hint=(1, 0.10))
        layout.add_widget(title)

        self.filter_box = GridLayout(cols=1, spacing=5, size_hint=(1, 0.18))
        layout.add_widget(self.filter_box)

        scroll = ScrollView(size_hint=(1, 0.57))
        self.notes_box = GridLayout(cols=1, spacing=6, size_hint_y=None)
        self.notes_box.bind(minimum_height=self.notes_box.setter("height"))
        scroll.add_widget(self.notes_box)
        layout.add_widget(scroll)

        bottom = BoxLayout(spacing=8, size_hint=(1, 0.15))

        for text, callback in [
            ("New", self.new_note),
            ("Open", self.open_note),
            ("Delete", self.delete_note),
            ("Types", self.open_types),
            ("Back", self.go_back),
        ]:
            btn = Button(text=text)
            btn.bind(on_press=callback)
            bottom.add_widget(btn)

        layout.add_widget(bottom)
        self.add_widget(layout)

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

        cols = 3 if len(filters) > 3 else len(filters)
        if cols < 1:
            cols = 1

        self.filter_box.cols = cols

        for name in filters:
            color = (0.25, 0.45, 0.75, 1) if name == self.current_filter else (0.12, 0.20, 0.35, 1)

            btn = Button(
                text=name,
                font_size=18,
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
            reverse=True)

        visible_files = []

        for file in files:
            data = self.read_note_data(file)
            if self.current_filter == "All" or data["type"] == self.current_filter:
                visible_files.append((file, data))

        if not visible_files:
            self.notes_box.add_widget(
                Label(
                    text="No notes found",
                    font_size=24,
                    size_hint_y=None,
                    height=80
                )
            )
            return

        for file, data in visible_files:
            preview = data["body"].replace("\n", " ").strip()
            if len(preview) > 60:
                preview = preview[:60] + "..."

            text = f"📄 {data['title']}\n{data['type']} | {preview}"

            btn = Button(
                text=text,
                font_size=18,
                size_hint_y=None,
                height=80,
                background_normal="",
                background_color=(0.12, 0.20, 0.35, 1)
            )

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