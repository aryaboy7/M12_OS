import json
from pathlib import Path

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label

from utils.logger import log
from utils.ui_scale import (
    title_font,
    button_font,
    list_font,
    input_font,
    row_height,
    input_height,
    button_height,
    padding_size,
    spacing_size,
)


BASE_DIR = Path(__file__).resolve().parent.parent
TYPES_FILE = BASE_DIR / "config" / "note_types.json"
TYPES_FILE.parent.mkdir(parents=True, exist_ok=True)


class NoteTypesScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.selected_type = None

        root = BoxLayout(
            orientation="vertical",
            spacing=spacing_size(),
            padding=padding_size(),
        )

        title = Label(
            text="Note Types",
            font_size=title_font(),
            bold=True,
            size_hint=(1, 0.10),
        )
        root.add_widget(title)

        self.type_input = TextInput(
            hint_text="New type name",
            font_size=input_font(),
            size_hint=(1, None),
            height=input_height(),
            multiline=False,
            use_bubble=False,
            use_handles=False,
        )
        root.add_widget(self.type_input)

        scroll = ScrollView(
            size_hint=(1, 0.60),
            do_scroll_x=False,
            do_scroll_y=True,
        )

        self.types_box = GridLayout(
            cols=1,
            spacing=spacing_size(),
            size_hint_y=None,
        )
        self.types_box.bind(
            minimum_height=self.types_box.setter("height")
        )

        scroll.add_widget(self.types_box)
        root.add_widget(scroll)

        bottom = BoxLayout(
            size_hint=(1, 0.18),
            spacing=spacing_size(),
        )

        add_btn = Button(
            text="Add",
            font_size=button_font(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
        )
        add_btn.bind(on_press=self.add_type)
        bottom.add_widget(add_btn)

        delete_btn = Button(
            text="Delete",
            font_size=button_font(),
            background_normal="",
            background_color=(0.35, 0.12, 0.12, 1),
        )
        delete_btn.bind(on_press=self.delete_type)
        bottom.add_widget(delete_btn)

        back_btn = Button(
            text="Back",
            font_size=button_font(),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1),
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
                font_size=list_font(),
                size_hint_y=None,
                height=row_height(),
                background_normal="",
                background_color=color,
                halign="center",
                valign="middle",
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
