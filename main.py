from kivy.config import Config

Config.set("kivy", "clipboard", "sdl2")

Config.set("graphics", "width", "900")
Config.set("graphics", "height", "650")
Config.set("graphics", "minimum_width", "900")
Config.set("graphics", "minimum_height", "650")
Config.set("graphics", "resizable", "0")


from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.screenmanager import ScreenManager
from kivy.utils import platform

from config.version import APP_NAME, VERSION

from utils.config_manager import ConfigManager
from utils.logger import log
from utils.event_notifier import EventNotifier
from utils.alarm_notifier import AlarmNotifier
from utils.ui_scale import font, height

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
from screens.backup_screen import BackupScreen
from screens.video_player_screen import VideoPlayerScreen


BluetoothScreen = None

try:
    from screens.bluetooth_screen import BluetoothScreen

except Exception as error:
    print(
        "Bluetooth screen unavailable: "
        f"{type(error).__name__}: {error}"
    )

    log.error(
        "Bluetooth screen import failed: "
        f"{type(error).__name__}: {error}"
    )


print("PLATFORM =", platform)
print("WINDOW WIDTH =", Window.width)
print("WINDOW HEIGHT =", Window.height)
print("DPI =", Window.dpi)

Window.clearcolor = (0.03, 0.04, 0.08, 1)

log.info(f"{APP_NAME} {VERSION} started")


class M12OS(App):
    def build(self):
        self.config_manager = ConfigManager()

        # ---------------------------------------------------------
        # Global application container
        # ---------------------------------------------------------
        root = FloatLayout()

        # ---------------------------------------------------------
        # Screen manager
        # ---------------------------------------------------------
        self.screen_manager = ScreenManager()

        self.screen_manager.add_widget(
            HomeScreen(name="home")
        )

        self.screen_manager.add_widget(
            NotesScreen(name="notes")
        )

        self.screen_manager.add_widget(
            NoteEditorScreen(name="editor")
        )

        self.screen_manager.add_widget(
            NoteTypesScreen(name="note_types")
        )

        self.screen_manager.add_widget(
            ClockScreen(name="clock")
        )

        self.screen_manager.add_widget(
            StopwatchScreen(name="stopwatch")
        )

        self.screen_manager.add_widget(
            TimerScreen(name="timer")
        )

        self.screen_manager.add_widget(
            SettingsScreen(name="settings")
        )

        self.screen_manager.add_widget(
            UpdaterScreen(name="updater")
        )

        self.screen_manager.add_widget(
            DrawingScreen(name="drawing")
        )

        self.screen_manager.add_widget(
            FilesScreen(name="files")
        )

        self.screen_manager.add_widget(
            MusicScreen(name="music")
        )

        self.screen_manager.add_widget(
            AIScreen(name="ai")
        )

        self.screen_manager.add_widget(
            WeatherScreen(name="weather")
        )

        self.screen_manager.add_widget(
            CalendarScreen(name="calendar")
        )

        self.screen_manager.add_widget(
            CalculatorConverterScreen(
                name="calculator"
            )
        )

        self.screen_manager.add_widget(
            AlarmScreen(name="alarm")
        )

        self.screen_manager.add_widget(
            BackupScreen(name="backup")
        )

        self.screen_manager.add_widget(
            VideoPlayerScreen(name="video_player")
        )

        if BluetoothScreen is not None:
            try:
                self.screen_manager.add_widget(
                    BluetoothScreen(name="bluetooth")
                )

            except Exception as error:
                log.error(
                    "Bluetooth screen creation failed: "
                    f"{type(error).__name__}: {error}"
                )

        start_screen = self.config_manager.get(
            "start_screen",
            "home",
        )

        if self.screen_manager.has_screen(start_screen):
            self.screen_manager.current = start_screen
        else:
            self.screen_manager.current = "home"

        root.add_widget(self.screen_manager)

        # ---------------------------------------------------------
        # Global AI button
        # ---------------------------------------------------------
        self.ai_button = Button(
            text="AI",
            font_size=font(22),
            bold=True,

            size_hint=(None, None),
            size=(height(68), height(54)),

            pos_hint={
                "right": 0.985,
                "top": 0.985,
            },

            background_normal="",
            background_down="",

            background_color=(
                0.20,
                0.35,
                0.85,
                0.96,
            ),

            color=(1, 1, 1, 1),
        )

        self.ai_button.bind(
            on_press=self.open_global_ai
        )

        root.add_widget(self.ai_button)

        # Keep the AI button above all screens.
        self.screen_manager.bind(
            current=self.update_ai_button
        )

        Window.set_title(
            f"W:{Window.width} "
            f"H:{Window.height} "
            f"DPI:{Window.dpi}"
        )

        print("================================")
        print("PLATFORM =", platform)
        print("WIDTH =", Window.width)
        print("HEIGHT =", Window.height)
        print("DPI =", Window.dpi)
        print("================================")

        # ---------------------------------------------------------
        # Event and alarm notification services
        # ---------------------------------------------------------
        self.event_notifier = EventNotifier(
            interval_seconds=30
        )
        self.event_notifier.start()

        self.alarm_notifier = AlarmNotifier(
            interval_seconds=30
        )
        self.alarm_notifier.start()

        # ---------------------------------------------------------
        # Bluetooth automatic connection
        # ---------------------------------------------------------
        try:
            if self.screen_manager.has_screen("bluetooth"):
                bluetooth_screen = (
                    self.screen_manager.get_screen(
                        "bluetooth"
                    )
                )

                Clock.schedule_once(
                    lambda dt: (
                        bluetooth_screen
                        .auto_connect_default()
                    ),
                    3,
                )

        except Exception as error:
            log.error(
                "Bluetooth auto-connect schedule failed: "
                f"{error}"
            )

        self.update_ai_button()

        return root

    # -------------------------------------------------------------
    # Open AI from any screen
    # -------------------------------------------------------------
    def open_global_ai(self, instance=None):
        manager = self.screen_manager

        if manager.current == "ai":
            return

        previous_screen = manager.current

        try:
            ai_screen = manager.get_screen("ai")

            # Save where the user came from.
            ai_screen.return_screen = previous_screen

        except Exception as error:
            log.error(
                f"Unable to prepare AI screen: {error}"
            )

        manager.current = "ai"

    # -------------------------------------------------------------
    # Hide the floating button while AI is already open
    # -------------------------------------------------------------
    def update_ai_button(self, *args):
        if not hasattr(self, "ai_button"):
            return

        on_ai_screen = (
            self.screen_manager.current == "ai"
        )

        self.ai_button.opacity = (
            0 if on_ai_screen else 1
        )

        self.ai_button.disabled = on_ai_screen

    # -------------------------------------------------------------
    # Stop services
    # -------------------------------------------------------------
    def on_stop(self):
        if hasattr(self, "event_notifier"):
            self.event_notifier.stop()

        if hasattr(self, "alarm_notifier"):
            self.alarm_notifier.stop()


if __name__ == "__main__":
    M12OS().run()
