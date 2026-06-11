import json
from pathlib import Path

from kivy.core.window import Window
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label

from utils.ui_scale import height
from utils.logger import log


BASE_DIR = Path(__file__).resolve().parent.parent
TYPES_FILE = BASE_DIR / "config" / "note_types.json"
TYPES_FILE.parent.mkdir(parents=True, exist_ok=True)


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


def types_font(base):
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


def row_height():
    profile = device_profile()

    if profile == "phone":
        return height(82)

    if profile == "tablet":
        return height(76)

    if profile == "m12":
        return height(70)

    return height(60)


class NoteTypesScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.selected_type = None

        profile = device_profile()

        if profile == "phone":
            title_hint = 0.10
            input_hint = 0.11
            list_hint = 0.59
            bottom_hint = 0.20
            title_size = 30
            input_size = 24
            button_size = 24
        elif profile == "tablet":
            title_hint = 0.10
            input_hint = 0.11
            list_hint = 0.59
            bottom_hint = 0.20
            title_size = 30
            input_size = 23
            button_size = 23
        elif profile == "m12":
            title_hint = 0.10
            input_hint = 0.11
            list_hint = 0.59
            bottom_hint = 0.20
            title_size = 28
            input_size = 21
            button_size = 21
        else:
            title_hint = 0.12
            input_hint = 0.12
            list_hint = 0.56
            bottom_hint = 0.20
            title_size = 32
            input_size = 24
            button_size = 22

        root = BoxLayout(
            orientation="vertical",
            spacing=height(10),
            padding=height(10)
        )

        title = Label(
            text="Note Types",
            font_size=types_font(title_size),
            bold=True,
            size_hint=(1, title_hint)
        )
        root.add_widget(title)

        self.type_input = TextInput(
            hint_text="New type name",
            font_size=types_font(input_size),
            size_hint=(1, input_hint),
            multiline=False,
            use_bubble=False,
            use_handles=False
        )
        root.add_widget(self.type_input)

        scroll = ScrollView(
            size_hint=(1, list_hint),
            do_scroll_x=False,
            do_scroll_y=True
        )

        self.types_box = GridLayout(
            cols=1,
            spacing=height(8),
            size_hint_y=None
        )
        self.types_box.bind(
            minimum_height=self.types_box.setter("height")
        )

        scroll.add_widget(self.types_box)
        root.add_widget(scroll)

        bottom = BoxLayout(
            size_hint=(1, bottom_hint),
            spacing=height(8)
        )

        add_btn = Button(
            text="Add",
            font_size=types_font(button_size),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        add_btn.bind(on_press=self.add_type)
        bottom.add_widget(add_btn)

        delete_btn = Button(
            text="Delete",
            font_size=types_font(button_size),
            background_normal="",
            background_color=(0.35, 0.12, 0.12, 1)
        )
        delete_btn.bind(on_press=self.delete_type)
        bottom.add_widget(delete_btn)

        back_btn = Button(
            text="Back",
            font_size=types_font(button_size),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        back_btn.bind(on_press=self.go_back)
        bottom.add_widget(back_btn)

        root.add_widget(bottom)
        self.add_widget(root)

    def on_enter(self):
        self.refresh_types()

    def load_types(self):
        try:
            if TYPES_FILE.exists():
                with open(TYPES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, list):
                    return data

        except Exception as e:
            log.error(f"Types: failed to load types: {e}")

        return ["Personal", "Work", "Project", "Shopping", "Idea"]

    def save_types(self, types):
        try:
            with open(TYPES_FILE, "w", encoding="utf-8") as f:
                json.dump(types, f, indent=4)

            log.info("Types: saved note_types.json")

        except Exception as e:
            log.error(f"Types: failed to save types: {e}")

    def refresh_types(self):
        self.types_box.clear_widgets()

        types = self.load_types()

        for note_type in types:
            color = (
                (0.25, 0.45, 0.75, 1)
                if note_type == self.selected_type
                else (0.12, 0.20, 0.35, 1)
            )

            btn = Button(
                text=note_type,
                font_size=types_font(22),
                size_hint_y=None,
                height=row_height(),
                background_normal="",
                background_color=color,
                halign="center",
                valign="middle"
            )
            btn.bind(size=lambda inst, val: setattr(inst, "text_size", val))

            btn.bind(on_press=lambda instance, t=note_type: self.select_type(t))
            self.types_box.add_widget(btn)

    def select_type(self, note_type):
        self.selected_type = note_type
        log.info(f"Types: selected {note_type}")
        self.refresh_types()

    def add_type(self, instance):
        name = self.type_input.text.strip()

        if not name:
            log.warning("Types: Add pressed with empty name")
            return

        types = self.load_types()

        if name not in types:
            types.append(name)
            self.save_types(types)
            log.info(f"Types: added {name}")

        else:
            log.warning(f"Types: already exists {name}")

        self.type_input.text = ""
        self.selected_type = name
        self.refresh_types()

    def delete_type(self, instance):
        if not self.selected_type:
            log.warning("Types: Delete pressed with no selection")
            return

        types = self.load_types()

        if self.selected_type in types:
            deleted = self.selected_type
            types.remove(deleted)
            self.save_types(types)
            log.info(f"Types: deleted {deleted}")

        self.selected_type = None
        self.refresh_types()

    def go_back(self, instance):
        log.info("Types: Back pressed")
        self.manager.current = "notes"
