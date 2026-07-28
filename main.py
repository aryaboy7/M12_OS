import sys

from kivy.config import Config


# ------------------------------------------------------------
# Platform-specific window configuration
# This must run before importing Window or other Kivy UI modules.
# ------------------------------------------------------------

IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"

if IS_LINUX:
    # Linux/Zorin: allow a large resizable window.
    Config.set("graphics", "resizable", "1")
    Config.set("graphics", "minimum_width", "900")
    Config.set("graphics", "minimum_height", "650")
else:
    # Existing desktop test size for macOS and other desktop systems.
    Config.set("graphics", "width", "900")
    Config.set("graphics", "height", "650")
    Config.set("graphics", "minimum_width", "900")
    Config.set("graphics", "minimum_height", "650")
    Config.set("graphics", "resizable", "0")


from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager
from kivy.utils import platform

from config.version import APP_NAME, VERSION
from utils.config_manager import ConfigManager
from utils.logger import log
from utils.event_notifier import EventNotifier
from utils.alarm_notifier import AlarmNotifier

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
    print("IMPORT: BluetoothScreen", flush=True)
    from screens.bluetooth_screen import BluetoothScreen
    print("IMPORT OK: BluetoothScreen", flush=True)
except Exception as error:
    print(
        f"IMPORT FAILED: BluetoothScreen: "
        f"{type(error).__name__}: {error}",
        flush=True
    )
    log.error(
        f"Bluetooth screen import failed: "
        f"{type(error).__name__}: {error}"
    )


print("PLATFORM =", platform, flush=True)
print("WINDOW WIDTH =", Window.width, flush=True)
print("WINDOW HEIGHT =", Window.height, flush=True)
print("DPI =", Window.dpi, flush=True)

Window.clearcolor = (0.03, 0.04, 0.08, 1)
log.info(f"{APP_NAME} {VERSION} started")


class M12OS(App):
    def add_screen_debug(self, sm, screen_class, name):
        print(f"START SCREEN: {name}", flush=True)

        try:
            screen = screen_class(name=name)
            print(f"CREATED SCREEN: {name}", flush=True)

            sm.add_widget(screen)
            print(f"ADDED SCREEN: {name}", flush=True)

        except Exception as error:
            print(
                f"FAILED SCREEN: {name}: "
                f"{type(error).__name__}: {error}",
                flush=True
            )
            log.error(
                f"Screen startup failed: {name}: "
                f"{type(error).__name__}: {error}"
            )

    def build(self):
        print("BUILD STARTED", flush=True)

        config = ConfigManager()
        print("CONFIG MANAGER READY", flush=True)

        sm = ScreenManager()
        print("SCREEN MANAGER READY", flush=True)

        self.add_screen_debug(sm, HomeScreen, "home")
        self.add_screen_debug(sm, NotesScreen, "notes")
        self.add_screen_debug(sm, NoteEditorScreen, "editor")
        self.add_screen_debug(sm, NoteTypesScreen, "note_types")
        self.add_screen_debug(sm, ClockScreen, "clock")
        self.add_screen_debug(sm, StopwatchScreen, "stopwatch")
        self.add_screen_debug(sm, TimerScreen, "timer")
        self.add_screen_debug(sm, SettingsScreen, "settings")
        self.add_screen_debug(sm, UpdaterScreen, "updater")
        self.add_screen_debug(sm, DrawingScreen, "drawing")
        self.add_screen_debug(sm, FilesScreen, "files")
        self.add_screen_debug(sm, MusicScreen, "music")
        self.add_screen_debug(sm, AIScreen, "ai")
        self.add_screen_debug(sm, WeatherScreen, "weather")
        self.add_screen_debug(sm, CalendarScreen, "calendar")
        self.add_screen_debug(sm, CalculatorConverterScreen, "calculator")
        self.add_screen_debug(sm, AlarmScreen, "alarm")
        self.add_screen_debug(sm, BackupScreen, "backup")
        self.add_screen_debug(sm, VideoPlayerScreen, "video_player")

        if BluetoothScreen is not None:
            self.add_screen_debug(sm, BluetoothScreen, "bluetooth")
        else:
            print("SKIPPED SCREEN: bluetooth", flush=True)

        print("ALL SCREENS PROCESSED", flush=True)

        start_screen = config.get("start_screen", "home")
        print(
            f"REQUESTED START SCREEN: {start_screen}",
            flush=True
        )

        sm.current = (
            start_screen
            if sm.has_screen(start_screen)
            else "home"
        )

        print(f"ACTIVE SCREEN: {sm.current}", flush=True)

        Window.set_title(
            f"{APP_NAME} {VERSION} | "
            f"W:{Window.width} H:{Window.height} DPI:{Window.dpi}"
        )

        print("================================", flush=True)
        print("APP =", APP_NAME, flush=True)
        print("VERSION =", VERSION, flush=True)
        print("PLATFORM =", platform, flush=True)
        print("WIDTH =", Window.width, flush=True)
        print("HEIGHT =", Window.height, flush=True)
        print("DPI =", Window.dpi, flush=True)
        print("================================", flush=True)

        self.event_notifier = None
        self.alarm_notifier = None

        print("STARTING EVENT NOTIFIER", flush=True)
        try:
            self.event_notifier = EventNotifier(
                interval_seconds=30
            )
            print("EVENT NOTIFIER CREATED", flush=True)

            self.event_notifier.start()
            print("EVENT NOTIFIER STARTED", flush=True)

        except Exception as error:
            print(
                f"EVENT NOTIFIER FAILED: "
                f"{type(error).__name__}: {error}",
                flush=True
            )
            log.error(
                f"Event notifier start failed: "
                f"{type(error).__name__}: {error}"
            )

        print("STARTING ALARM NOTIFIER", flush=True)
        try:
            self.alarm_notifier = AlarmNotifier(
                interval_seconds=30
            )
            print("ALARM NOTIFIER CREATED", flush=True)

            self.alarm_notifier.start()
            print("ALARM NOTIFIER STARTED", flush=True)

        except Exception as error:
            print(
                f"ALARM NOTIFIER FAILED: "
                f"{type(error).__name__}: {error}",
                flush=True
            )
            log.error(
                f"Alarm notifier start failed: "
                f"{type(error).__name__}: {error}"
            )

        if platform == "android" and sm.has_screen("bluetooth"):
            print(
                "SCHEDULING BLUETOOTH AUTO CONNECT",
                flush=True
            )

            try:
                bt_screen = sm.get_screen("bluetooth")

                Clock.schedule_once(
                    lambda dt: bt_screen.auto_connect_default(),
                    3
                )

                print(
                    "BLUETOOTH AUTO CONNECT SCHEDULED",
                    flush=True
                )

            except Exception as error:
                print(
                    f"BLUETOOTH AUTO CONNECT FAILED: "
                    f"{type(error).__name__}: {error}",
                    flush=True
                )
                log.error(
                    f"Bluetooth auto connect schedule failed: "
                    f"{type(error).__name__}: {error}"
                )
        else:
            print(
                "BLUETOOTH AUTO CONNECT SKIPPED",
                flush=True
            )

        print("BUILD FINISHED", flush=True)
        return sm

    def maximize_linux_window(self, dt):
        """
        Maximize the Kivy window after it has been created.

        Calling maximize shortly after startup is more reliable on
        Linux desktop environments than setting a fixed large size.
        """
        if platform != "linux":
            return

        try:
            Window.maximize()
            print(
                f"LINUX WINDOW MAXIMIZED: "
                f"{Window.width} x {Window.height}",
                flush=True
            )
        except Exception as error:
            print(
                f"LINUX WINDOW MAXIMIZE FAILED: "
                f"{type(error).__name__}: {error}",
                flush=True
            )

            # Safe fallback for desktop environments that do not
            # implement Window.maximize().
            try:
                Window.size = (1400, 900)
                print(
                    "LINUX WINDOW FALLBACK SIZE: 1400 x 900",
                    flush=True
                )
            except Exception as fallback_error:
                log.error(
                    f"Linux window sizing failed: "
                    f"{type(fallback_error).__name__}: "
                    f"{fallback_error}"
                )

    def on_start(self):
        print("APP ON_START", flush=True)

        if platform == "linux":
            Clock.schedule_once(
                self.maximize_linux_window,
                0.15
            )

    def on_pause(self):
        print("APP ON_PAUSE", flush=True)
        return True

    def on_resume(self):
        print("APP ON_RESUME", flush=True)

    def on_stop(self):
        print("APP ON_STOP", flush=True)

        try:
            if self.event_notifier is not None:
                self.event_notifier.stop()
                print(
                    "EVENT NOTIFIER STOPPED",
                    flush=True
                )
        except Exception as error:
            print(
                f"EVENT NOTIFIER STOP FAILED: "
                f"{type(error).__name__}: {error}",
                flush=True
            )
            log.error(
                f"Event notifier stop failed: "
                f"{type(error).__name__}: {error}"
            )

        try:
            if self.alarm_notifier is not None:
                self.alarm_notifier.stop()
                print(
                    "ALARM NOTIFIER STOPPED",
                    flush=True
                )
        except Exception as error:
            print(
                f"ALARM NOTIFIER STOP FAILED: "
                f"{type(error).__name__}: {error}",
                flush=True
            )
            log.error(
                f"Alarm notifier stop failed: "
                f"{type(error).__name__}: {error}"
            )


if __name__ == "__main__":
    print("STARTING M12 OS", flush=True)
    M12OS().run()