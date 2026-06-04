from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager
from screens.note_types_screen import NoteTypesScreen
from config.version import APP_NAME, VERSION
from utils.logger import log
from screens.home_screen import HomeScreen
from screens.notes_screen import NotesScreen
from screens.note_editor_screen import NoteEditorScreen

Window.clearcolor = (0.03, 0.04, 0.08, 1)

log.info(f"{APP_NAME} {VERSION} started")


class M12OS(App):
    def build(self):
     sm = ScreenManager()
     sm.add_widget(HomeScreen(name="home"))
     sm.add_widget(NotesScreen(name="notes"))
     sm.add_widget(NoteEditorScreen(name="editor"))
     sm.add_widget(NoteTypesScreen(name="note_types"))
     return sm


M12OS().run()