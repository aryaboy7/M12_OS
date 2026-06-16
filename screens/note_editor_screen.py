import json
from pathlib import Path

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.label import Label

from utils.logger import log
from utils.text_editor_popup import open_text_editor
from utils.ui_scale import (
    device_profile,
    button_font,
    input_font,
    text_font,
    title_font,
    button_height,
    input_height,
    padding_size,
    spacing_size,
    height,
)


Window.softinput_mode = "resize"


BASE_DIR = Path(__file__).resolve().parent.parent
NOTES_DIR = BASE_DIR / "data" / "notes"
TYPES_FILE = BASE_DIR / "config" / "note_types.json"
NOTES_DIR.mkdir(parents=True, exist_ok=True)


def body_editor_height():
    profile = device_profile()

    if profile == "phone":
        return 760
    if profile == "tablet":
        return 560
    if profile == "m12":
        return 480

    return height(360)


def popup_font():
    profile = device_profile()

    if profile == "phone":
        return 52
    if profile == "tablet":
        return 36
    if profile == "m12":
        return 28

    return text_font()


class NoteEditorScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.current_path = None
        self.saved_popup = None

        root = BoxLayout(
            orientation="vertical",
            spacing=spacing_size(),
            padding=padding_size(),
        )

        top = BoxLayout(
            spacing=spacing_size(),
            size_hint=(1, None),
            height=button_height(),
        )

        back_btn = Button(
            text="< Back",
            font_size=button_font(),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1),
        )
        back_btn.bind(on_press=self.go_back)

        save_btn = Button(
            text="Save",
            font_size=button_font(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
        )
        save_btn.bind(on_press=self.save_note)

        top.add_widget(back_btn)
        top.add_widget(save_btn)
        root.add_widget(top)

        self.scroll = ScrollView(
            do_scroll_x=False,
            do_scroll_y=True,
            size_hint=(1, 1),
        )

        form = BoxLayout(
            orientation="vertical",
            spacing=spacing_size(),
            size_hint_y=None,
        )
        form.bind(minimum_height=form.setter("height"))

        self.title_input = TextInput(
            hint_text="Note title",
            font_size=input_font(),
            size_hint=(1, None),
            height=input_height(),
            multiline=False,
            use_bubble=False,
            use_handles=False,
            readonly=(device_profile() == "m12"),
        )

        if device_profile() == "m12":
            self.title_input.bind(on_touch_down=self.title_touched)

        form.add_widget(self.title_input)

        self.type_spinner = Spinner(
            text="Personal",
            values=self.load_types(),
            font_size=button_font(),
            size_hint=(1, None),
            height=input_height(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
        )
        form.add_widget(self.type_spinner)

        self.body_input = TextInput(
            hint_text="Type note here...",
            font_size=text_font(),
            size_hint=(1, None),
            height=body_editor_height(),
            multiline=True,
            use_bubble=False,
            use_handles=False,
            readonly=(device_profile() == "m12"),
        )

        if device_profile() == "m12":
            self.body_input.bind(on_touch_down=self.body_touched)
        else:
            self.body_input.bind(focus=self.on_body_focus)

        form.add_widget(self.body_input)

        form.add_widget(BoxLayout(size_hint=(1, None), height=button_height()))

        self.scroll.add_widget(form)
        root.add_widget(self.scroll)

        self.add_widget(root)

    def on_body_focus(self, instance, focused):
        if focused:
            self.scroll.scroll_y = 0.0

    def title_touched(self, instance, touch):
        if instance.collide_point(*touch.pos):
            self.open_title_editor()
            return True
        return False

    def body_touched(self, instance, touch):
        if instance.collide_point(*touch.pos):
            self.open_body_editor()
            return True
        return False

    def open_title_editor(self):
        def save_text(value):
            self.title_input.text = value

        open_text_editor(
            title="Note Title",
            text=self.title_input.text,
            on_save=save_text,
            multiline=False,
        )

    def open_body_editor(self):
        def save_text(value):
            self.body_input.text = value

        open_text_editor(
            title="Note Text",
            text=self.body_input.text,
            on_save=save_text,
            multiline=True,
        )

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

    def show_saved_then_back(self):
        box = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size(),
        )

        label = Label(
            text="Note saved",
            font_size=popup_font(),
            bold=True,
            halign="center",
            valign="middle",
        )
        label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        box.add_widget(label)

        self.saved_popup = Popup(
            title="Saved",
            content=box,
            size_hint=(0.80, 0.30),
            auto_dismiss=False,
        )

        self.saved_popup.open()
        Clock.schedule_once(self.close_saved_popup_and_back, 0.7)

    def close_saved_popup_and_back(self, dt):
        try:
            if self.saved_popup:
                self.saved_popup.dismiss()
        except Exception:
            pass

        self.saved_popup = None
        self.go_back(None)

    def save_note(self, instance):
        title = self.title_input.text.strip() or "Untitled"
        note_type = self.type_spinner.text.strip() or "Personal"
        body = self.body_input.text

        data = {
            "title": title,
            "type": note_type,
            "body": body,
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
            self.show_saved_then_back()

        except Exception as e:
            log.error(f"Editor: failed to save note: {e}")

    def go_back(self, instance):
        log.info("Editor: Back pressed")
        self.manager.current = "notes"
