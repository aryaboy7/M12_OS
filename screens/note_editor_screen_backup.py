from pathlib import Path

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput

from utils.logger import log


BASE_DIR = Path(__file__).resolve().parent.parent
NOTES_DIR = BASE_DIR / "data" / "notes"
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
            font_size=28,
            size_hint=(1, 0.14),
            multiline=False
        )
        root.add_widget(self.title_input)

        self.body_input = TextInput(
            hint_text="Type note here...",
            font_size=22,
            size_hint=(1, 0.74),
            multiline=True
        )
        root.add_widget(self.body_input)

        self.add_widget(root)

    def new_note(self):
        self.current_path = None
        self.title_input.text = ""
        self.body_input.text = ""
        log.info("Editor: new note")

    def load_note(self, path):
        self.current_path = Path(path)
        self.title_input.text = self.current_path.stem

        try:
            self.body_input.text = self.current_path.read_text(encoding="utf-8")
            log.info(f"Editor: loaded {self.current_path.name}")
        except Exception as e:
            log.error(f"Editor: failed to load note: {e}")
            self.body_input.text = ""

    def save_note(self, instance):
        title = self.title_input.text.strip() or "Untitled"
        safe_title = title.replace("/", "_").replace("\\", "_")
        path = NOTES_DIR / f"{safe_title}.txt"

        try:
            path.write_text(self.body_input.text, encoding="utf-8")
            self.current_path = path
            log.info(f"Editor: saved {path.name}")
        except Exception as e:
            log.error(f"Editor: failed to save note: {e}")

    def go_back(self, instance):
        log.info("Editor: Back pressed")
        self.manager.current = "notes"