from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager

from config.version import APP_NAME, VERSION
from utils.config_manager import ConfigManager
from utils.logger import log

from screens.home_screen import HomeScreen
from screens.notes_screen import NotesScreen
from screens.note_editor_screen import NoteEditorScreen
from screens.note_types_screen import NoteTypesScreen
from screens.clock_screen import ClockScreen
from screens.stopwatch_screen import StopwatchScreen
from screens.timer_screen import TimerScreen
from screens.settings_screen import SettingsScreen
from screens.updater_screen import UpdaterScreen
from screens.drawing_screen import DrawingScreen
from screens.files_screen import FilesScreen
from screens.music_screen import MusicScreen
from screens.ai_screen import AIScreen
from screens.weather_screen import WeatherScreen

Window.clearcolor = (0.03, 0.04, 0.08, 1)

log.info(f"{APP_NAME} {VERSION} started")


class M12OS(App):
    def build(self):
        config = ConfigManager()

        sm = ScreenManager()
        sm.add_widget(HomeScreen(name="home"))
        sm.add_widget(NotesScreen(name="notes"))
        sm.add_widget(NoteEditorScreen(name="editor"))
        sm.add_widget(NoteTypesScreen(name="note_types"))
        sm.add_widget(ClockScreen(name="clock"))
        sm.add_widget(StopwatchScreen(name="stopwatch"))
        sm.add_widget(TimerScreen(name="timer"))
        sm.add_widget(SettingsScreen(name="settings"))
        sm.add_widget(UpdaterScreen(name="updater"))
        sm.add_widget(DrawingScreen(name="drawing"))
        sm.add_widget(FilesScreen(name="files"))
        sm.add_widget(MusicScreen(name="music"))
        sm.add_widget(AIScreen(name="ai"))
        sm.add_widget(WeatherScreen(name="weather"))

        start_screen = config.get("start_screen", "home")
        sm.current = start_screen if sm.has_screen(start_screen) else "home"
        return sm


if __name__ == "__main__":
    M12OS().run()
