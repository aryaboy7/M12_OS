from kivy.config import Config

Config.set("kivy", "clipboard", "sdl2")

Config.set("graphics", "width", "900")
Config.set("graphics", "height", "650")
Config.set("graphics", "minimum_width", "900")
Config.set("graphics", "minimum_height", "650")
Config.set("graphics", "resizable", "0")

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager
from kivy.utils import platform

from config.version import APP_NAME, VERSION
from utils.config_manager import ConfigManager
from utils.logger import log
from utils.event_notifier import EventNotifier

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
from screens.calendar_screen import CalendarScreen
from screens.calculator_converter_screen import CalculatorConverterScreen
from screens.alarm_screen import AlarmScreen
from utils.alarm_notifier import AlarmNotifier

print("PLATFORM =", platform)
print("WINDOW WIDTH =", Window.width)
print("WINDOW HEIGHT =", Window.height)
print("DPI =", Window.dpi)

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
        sm.add_widget(CalendarScreen(name="calendar"))
        sm.add_widget(CalculatorConverterScreen(name="calculator"))
        sm.add_widget(AlarmScreen(name="alarm"))

        start_screen = config.get("start_screen", "home")
        sm.current = start_screen if sm.has_screen(start_screen) else "home"

        Window.set_title(f"W:{Window.width} H:{Window.height} DPI:{Window.dpi}")

        print("================================")
        print("PLATFORM =", platform)
        print("WIDTH =", Window.width)
        print("HEIGHT =", Window.height)
        print("DPI =", Window.dpi)
        print("================================")

        self.event_notifier = EventNotifier(interval_seconds=30)
        self.event_notifier.start()
        self.alarm_notifier = AlarmNotifier(interval_seconds=30)
        self.alarm_notifier.start()

        return sm

    def on_stop(self):
        if hasattr(self, "event_notifier"):
            self.event_notifier.stop()
        if hasattr(self, "alarm_notifier"):
            self.alarm_notifier.stop()

if __name__ == "__main__":
    M12OS().run()
