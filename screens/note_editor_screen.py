import json
from pathlib import Path

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner

from utils.logger import log


BASE_DIR = Path(__file__).resolve().parent.parent
NOTES_DIR = BASE_DIR / "data" / "notes"
TYPES_FILE = BASE_DIR / "config" / "note_types.json"
NOTES_DIR.mkdir(parents=True, exist_ok=True)


class NoteEditorScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_path = None

        root = BoxLayout(orientation="vertical", spacing=10, padding=10)

        top = BoxLayout(size_hint=(1, 0.12))

        back_btn = Button(text="< Back")
        back_btn.bind(on_press=self.go_back)

        save_btn = Button(text="Save")
        save_btn.bind(on_press=self.save_note)

        top.add_widget(back_btn)
        top.add_widget(save_btn)
        root.add_widget(top)

        self.title_input = TextInput(
            hint_text="Note title",
            font_size=26,
            size_hint=(1, 0.12),
            multiline=False
        )
        root.add_widget(self.title_input)

        self.type_spinner = Spinner(
            text="Personal",
            values=self.load_types(),
            font_size=22,
            size_hint=(1, 0.10),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        root.add_widget(self.type_spinner)

        self.body_input = TextInput(
            hint_text="Type note here...",
            font_size=22,
            size_hint=(1, 0.66),
            multiline=True
        )
        root.add_widget(self.body_input)

        self.add_widget(root)

    def load_types(self):
        try:
            if TYPES_FILE.exists():
                data = json.loads(TYPES_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    return data
        except Exception as e:
            log.error(f"Editor: failed to load types: {e}")

        return ["Personal", "Work", "Project", "Shopping", "Idea"]

    def refresh_type_spinner(self):
        types = self.load_types()
        self.type_spinner.values = types

        if self.type_spinner.text not in types:
            self.type_spinner.text = types[0] if types else "Personal"

    def new_note(self):
        types = self.load_types()
        self.current_path = None
        self.title_input.text = ""
        self.type_spinner.values = types
        self.type_spinner.text = types[0] if types else "Personal"
        self.body_input.text = ""
        log.info("Editor: new note")

    def load_note(self, path):
        self.current_path = Path(path)
        types = self.load_types()
        self.type_spinner.values = types

        try:
            data = json.loads(self.current_path.read_text(encoding="utf-8"))

            note_type = data.get("type", types[0] if types else "Personal")

            self.title_input.text = data.get("title", self.current_path.stem)
            self.type_spinner.text = note_type
            self.body_input.text = data.get("body", "")

            log.info(f"Editor: loaded {self.current_path.name}")

        except Exception as e:
            log.error(f"Editor: failed to load note JSON: {e}")
            self.title_input.text = self.current_path.stem
            self.type_spinner.text = types[0] if types else "Personal"

            try:
                self.body_input.text = self.current_path.read_text(encoding="utf-8")
            except Exception:
                self.body_input.text = ""

    def save_note(self, instance):
        title = self.title_input.text.strip() or "Untitled"
        note_type = self.type_spinner.text.strip() or "Personal"
        body = self.body_input.text

        data = {
            "title": title,
            "type": note_type,
            "body": body
        }

        if self.current_path:
            path = self.current_path
        else:
            safe_title = title.replace("/", "_").replace("\\", "_")
            path = NOTES_DIR / f"{safe_title}.json"

        try:
            path.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self.current_path = path
            log.info(f"Editor: saved {path.name}")
        except Exception as e:
            log.error(f"Editor: failed to save note: {e}")

    def go_back(self, instance):
        log.info("Editor: Back pressed")
        self.manager.current = "notes"