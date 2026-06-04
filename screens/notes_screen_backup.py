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
NOTES_DIR.mkdir(parents=True, exist_ok=True)


class NotesScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_note = None

        layout = BoxLayout(
            orientation="vertical",
            spacing=10,
            padding=10
        )

        title = Label(
            text="Notes",
            font_size=32,
            size_hint=(1, 0.12)
        )
        layout.add_widget(title)

        scroll = ScrollView(size_hint=(1, 0.73))

        self.notes_box = GridLayout(
            cols=1,
            spacing=6,
            size_hint_y=None
        )

        self.notes_box.bind(
            minimum_height=self.notes_box.setter("height")
        )

        scroll.add_widget(self.notes_box)
        layout.add_widget(scroll)

        bottom = BoxLayout(
            spacing=8,
            size_hint=(1, 0.15)
        )

        new_btn = Button(text="New")
        new_btn.bind(on_press=self.new_note)
        bottom.add_widget(new_btn)

        open_btn = Button(text="Open")
        open_btn.bind(on_press=self.open_note)
        bottom.add_widget(open_btn)

        delete_btn = Button(text="Delete")
        delete_btn.bind(on_press=self.delete_note)
        bottom.add_widget(delete_btn)

        back_btn = Button(text="Back")
        back_btn.bind(on_press=self.go_back)
        bottom.add_widget(back_btn)

        types_btn = Button(text="Types")
        types_btn.bind(on_press=self.open_types)
        bottom.add_widget(types_btn)

        layout.add_widget(bottom)
        self.add_widget(layout)


    def on_enter(self):
        self.refresh_notes()

    def refresh_notes(self):
        self.notes_box.clear_widgets()

        files = sorted(NOTES_DIR.glob("*.txt"))

        if not files:
            empty = Label(
                text="No notes yet",
                font_size=24,
                size_hint_y=None,
                height=80
            )
            self.notes_box.add_widget(empty)
            return

        for file in files:
            btn = Button(
                text="📄  " + file.stem,
                font_size=20,
                size_hint_y=None,
                height=60,
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

    def go_back(self, instance):
        log.info("Notes: Back pressed")
        self.manager.current = "home"
        
    def open_types(self, instance):
        log.info("Notes: Types pressed")
        self.manager.current = "note_types"
