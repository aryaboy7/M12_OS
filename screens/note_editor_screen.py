import json
from pathlib import Path

from kivy.core.window import Window
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView

from utils.ui_scale import font, height
from utils.logger import log


Window.softinput_mode = "resize"


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


def editor_font(base):
    profile = device_profile()

    if profile == "phone":
        scale = 1.75
    elif profile == "tablet":
        scale = 1.45
    elif profile == "m12":
        scale = 1.30
    else:
        scale = 1.00

    return max(14, int(base * scale))


class NoteEditorScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.current_path = None

        profile = device_profile()

        if profile == "phone":
            button_size = 24
            title_size = 24
            type_size = 22
            body_size = 24
            body_height = 520
        elif profile == "tablet":
            button_size = 23
            title_size = 23
            type_size = 21
            body_size = 23
            body_height = 500
        elif profile == "m12":
            button_size = 24
            title_size = 26
            type_size = 24
            body_size = 28
            body_height = 430
        else:
            button_size = 22
            title_size = 28
            type_size = 22
            body_size = 22
            body_height = 360

        root = BoxLayout(
            orientation="vertical",
            spacing=height(8),
            padding=height(8)
        )

        top = BoxLayout(
            spacing=height(8),
            size_hint=(1, None),
            height=height(62)
        )

        back_btn = Button(
            text="< Back",
            font_size=editor_font(button_size),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        back_btn.bind(on_press=self.go_back)

        save_btn = Button(
            text="Save",
            font_size=editor_font(button_size),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        save_btn.bind(on_press=self.save_note)

        top.add_widget(back_btn)
        top.add_widget(save_btn)
        root.add_widget(top)

        self.scroll = ScrollView(
            do_scroll_x=False,
            do_scroll_y=True,
            size_hint=(1, 1)
        )

        form = BoxLayout(
            orientation="vertical",
            spacing=height(8),
            size_hint_y=None
        )
        form.bind(minimum_height=form.setter("height"))

        self.title_input = TextInput(
            hint_text="Note title",
            font_size=editor_font(title_size),
            size_hint=(1, None),
            height=height(62),
            multiline=False,
            use_bubble=False,
            use_handles=False
        )
        form.add_widget(self.title_input)

        self.type_spinner = Spinner(
            text="Personal",
            values=self.load_types(),
            font_size=editor_font(type_size),
            size_hint=(1, None),
            height=height(58),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        form.add_widget(self.type_spinner)

        self.body_input = TextInput(
            hint_text="Type note here...",
            font_size=editor_font(body_size),
            size_hint=(1, None),
            height=height(body_height),
            multiline=True,
            use_bubble=False,
            use_handles=False
        )
        self.body_input.bind(focus=self.on_body_focus)
        form.add_widget(self.body_input)

        form.add_widget(BoxLayout(size_hint=(1, None), height=height(120)))

        self.scroll.add_widget(form)
        root.add_widget(self.scroll)

        self.add_widget(root)

    def on_body_focus(self, instance, focused):
        if focused:
            self.scroll.scroll_y = 0.0

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
