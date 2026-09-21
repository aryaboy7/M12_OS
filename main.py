import sys
import subprocess

from kivy.config import Config

Config.set("kivy", "clipboard", "sdl2")

# -------------------------------------------------------------
# Platform-specific window configuration
# -------------------------------------------------------------
IS_LINUX = sys.platform.startswith("linux")


def _linux_system_screen_size():
    """
    Return the current Linux display size reported by the system.

    xrandr is queried before Kivy creates its window, so the initial
    M12 window can be sized from the actual display instead of a
    hardcoded desktop resolution.
    """
    try:
        result = subprocess.run(
            ["xrandr", "--current"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )

        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "*" not in line:
                    continue

                for part in line.split():
                    if "x" not in part:
                        continue

                    pieces = part.split("x", 1)
                    if (
                        len(pieces) == 2
                        and pieces[0].isdigit()
                        and pieces[1].isdigit()
                    ):
                        width = int(pieces[0])
                        height = int(pieces[1])

                        if width >= 640 and height >= 480:
                            return width, height
    except Exception:
        pass

    return None


if IS_LINUX:
    detected_screen = _linux_system_screen_size()

    if detected_screen is not None:
        screen_width, screen_height = detected_screen

        # Use most of the available display while leaving room for the
        # desktop panel, window borders, and normal window management.
        window_width = int(screen_width * 0.75)
        window_height = int(screen_height * 0.80)

        # Keep the application usable on unusually small/large displays.
        window_width = max(900, min(window_width, screen_width - 80))
        window_height = max(650, min(window_height, screen_height - 100))
    else:
        # Safe fallback if the Linux display server cannot be queried.
        window_width = 1000
        window_height = 700

    Config.set("graphics", "width", str(window_width))
    Config.set("graphics", "height", str(window_height))
    Config.set("graphics", "minimum_width", "900")
    Config.set("graphics", "minimum_height", "650")
    Config.set("graphics", "resizable", "1")
    Config.set("graphics", "borderless", "0")
    Config.set("graphics", "fullscreen", "0")
else:
    # Preserve existing behavior on macOS and other desktop platforms.
    Config.set("graphics", "width", "900")
    Config.set("graphics", "height", "650")
    Config.set("graphics", "minimum_width", "900")
    Config.set("graphics", "minimum_height", "650")
    Config.set("graphics", "resizable", "0")
    Config.set("graphics", "fullscreen", "0")

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
from utils.data_paths import EVENTS_FILE, ALARMS_FILE

from screens.home_screen import HomeScreen
from screens.owner_voice_enrollment_screen import OwnerVoiceEnrollmentScreen
from services.owner_voice_enrollment import OwnerVoiceEnrollmentService
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
from screens.brainstorm_screen import BrainstormScreen
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
        self.root_container = FloatLayout()

        # ScreenManager is intentionally created later on Linux.
        #
        # Linux window managers apply the real maximized/work-area size
        # only after the Kivy window exists. Building every screen before
        # that happens causes font/height helpers to use the wrong size.
        #
        # On non-Linux platforms we keep the existing immediate startup.
        self.screen_manager = None

        if not IS_LINUX:
            self._build_screen_manager()

        self.update_window_title()

        print("================================")
        print("PLATFORM =", platform)
        print("WIDTH =", Window.width)
        print("HEIGHT =", Window.height)
        print("DPI =", Window.dpi)
        print("LINUX =", IS_LINUX)
        if IS_LINUX:
            print("F11 FULLSCREEN = ENABLED")
        print("================================")

        # ---------------------------------------------------------
        # Event and alarm notification services
        # ---------------------------------------------------------
        self.event_notifier = EventNotifier(interval_seconds=30)
        self.event_notifier.start()

        self.alarm_notifier = AlarmNotifier(interval_seconds=30)
        self.alarm_notifier.start()

        if not IS_LINUX:
            self._schedule_bluetooth_auto_connect()

        return self.root_container

    def _build_screen_manager(self):
        """
        Build all application screens using the CURRENT Window size.

        On Linux this is called only after the window manager has applied
        the final maximized/work-area dimensions. That means every
        ui_scale helper sees the real usable window instead of the smaller
        pre-maximize startup window.
        """
        if self.screen_manager is not None:
            return

        manager = ScreenManager()

        manager.add_widget(
            OwnerVoiceEnrollmentScreen(name="owner_voice_enrollment")
        )
        manager.add_widget(HomeScreen(name="home"))
        manager.add_widget(NotesScreen(name="notes"))
        manager.add_widget(NoteEditorScreen(name="editor"))
        manager.add_widget(NoteTypesScreen(name="note_types"))
        manager.add_widget(ClockScreen(name="clock"))
        manager.add_widget(StopwatchScreen(name="stopwatch"))
        manager.add_widget(TimerScreen(name="timer"))
        manager.add_widget(SettingsScreen(name="settings"))
        manager.add_widget(UpdaterScreen(name="updater"))
        manager.add_widget(DrawingScreen(name="drawing"))
        manager.add_widget(FilesScreen(name="files"))
        manager.add_widget(MusicScreen(name="music"))
        manager.add_widget(AIScreen(name="ai"))
        manager.add_widget(BrainstormScreen(name="brainstorm"))
        manager.add_widget(WeatherScreen(name="weather"))
        manager.add_widget(CalendarScreen(name="calendar"))
        manager.add_widget(
            CalculatorConverterScreen(name="calculator")
        )
        manager.add_widget(AlarmScreen(name="alarm"))
        manager.add_widget(BackupScreen(name="backup"))
        manager.add_widget(VideoPlayerScreen(name="video_player"))

        if BluetoothScreen is not None:
            try:
                manager.add_widget(
                    BluetoothScreen(name="bluetooth")
                )
            except Exception as error:
                log.error(
                    "Bluetooth screen creation failed: "
                    f"{type(error).__name__}: {error}"
                )

        owner_enrollment = OwnerVoiceEnrollmentService()

        if not owner_enrollment.profile_exists():
            # First-run / missing-profile behavior:
            # always show the owner enrollment screen before normal M12 use.
            manager.current = "owner_voice_enrollment"
            log.info(
                "Owner voice profile missing; opening enrollment screen."
            )
        else:
            start_screen = self.config_manager.get(
                "start_screen",
                "home",
            )

            if manager.has_screen(start_screen):
                manager.current = start_screen
            else:
                manager.current = "home"

        self.screen_manager = manager
        self.root_container.add_widget(manager)

    def _schedule_bluetooth_auto_connect(self):
        try:
            if (
                self.screen_manager is not None
                and self.screen_manager.has_screen("bluetooth")
            ):
                bluetooth_screen = self.screen_manager.get_screen("bluetooth")
                Clock.schedule_once(
                    lambda dt: bluetooth_screen.auto_connect_default(),
                    3,
                )
        except Exception as error:
            log.error(f"Bluetooth auto-connect schedule failed: {error}")


    # -------------------------------------------------------------
    # Linux window setup
    # -------------------------------------------------------------
    def on_start(self):
        if IS_LINUX:
            Window.bind(on_key_down=self.on_window_key_down)
            Window.bind(size=self.on_window_size)

            try:
                Window.minimum_width = 900
                Window.minimum_height = 650
            except Exception:
                pass

            # IMPORTANT:
            # Maximize before constructing any screen. Screen constructors
            # call ui_scale helpers, so they must see the final usable
            # Window dimensions.
            self._maximize_linux_window()
        else:
            self.update_window_title()

            if platform == "android":
                Clock.schedule_once(
                    self._restore_android_native_alarms,
                    1.0,
                )

    def _restore_android_native_alarms(self, dt=0):
        """Re-register saved Calendar events and Clock alarms on Android."""
        if platform != "android":
            return

        import json

        try:
            from services.android_event_alarm_scheduler import (
                sync_android_event_alarms,
            )

            events = []
            if EVENTS_FILE.exists():
                data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    events = data

            sync_android_event_alarms(events)
            log.info(
                "Android startup event alarm sync completed: "
                f"{len(events)} saved event(s)."
            )
        except Exception as error:
            log.error(
                "Android startup event alarm sync failed: "
                f"{type(error).__name__}: {error}"
            )

        try:
            from services.android_clock_alarm_scheduler import (
                sync_android_clock_alarms,
            )

            alarms = []
            if ALARMS_FILE.exists():
                data = json.loads(ALARMS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    alarms = data

            sync_android_clock_alarms(alarms)
            log.info(
                "Android startup clock alarm sync completed: "
                f"{len(alarms)} saved alarm(s)."
            )
        except Exception as error:
            log.error(
                "Android startup clock alarm sync failed: "
                f"{type(error).__name__}: {error}"
            )

    def _maximize_linux_window(self, dt=0):
        if not IS_LINUX:
            return

        try:
            maximize = getattr(Window, "maximize", None)
            if callable(maximize):
                maximize()

                # Give the Linux window manager time to apply the actual
                # work-area size. Only then build the screens.
                Clock.schedule_once(self._finish_linux_startup, 0.40)
            else:
                log.warning("Linux window maximize is not available.")
                Clock.schedule_once(self._finish_linux_startup, 0)
        except Exception as error:
            log.error(
                f"Linux maximize failed: {type(error).__name__}: {error}"
            )
            Clock.schedule_once(self._finish_linux_startup, 0)

    def _finish_linux_startup(self, dt=0):
        if self.screen_manager is None:
            self._build_screen_manager()
            self._schedule_bluetooth_auto_connect()

        self.update_window_title()

        log.info(
            f"Linux window ready: "
            f"{int(Window.width)}x{int(Window.height)}"
        )


    # -------------------------------------------------------------
    # Linux keyboard handling
    # -------------------------------------------------------------
    def on_window_key_down(self, window, key, scancode, codepoint, modifiers):
        if not IS_LINUX:
            return False

        # F11
        if key == 292:
            self.toggle_fullscreen()
            return True

        return False

    # -------------------------------------------------------------
    # Linux fullscreen
    # -------------------------------------------------------------
    def toggle_fullscreen(self):
        if not IS_LINUX:
            return

        try:
            if Window.fullscreen:
                Window.fullscreen = False
            else:
                Window.fullscreen = "auto"

            Clock.schedule_once(lambda dt: self.update_window_title(), 0.15)

            log.info(f"Linux fullscreen: {Window.fullscreen}")

        except Exception as error:
            log.error(
                f"Fullscreen toggle failed: {type(error).__name__}: {error}"
            )

    # -------------------------------------------------------------
    # Window size changed
    # -------------------------------------------------------------
    def on_window_size(self, *args):
        self.update_window_title()

    # -------------------------------------------------------------
    # Window title
    # -------------------------------------------------------------
    def update_window_title(self):
        mode = "Fullscreen" if Window.fullscreen else "Windowed"

        Window.set_title(
            f"{APP_NAME} {VERSION} | "
            f"{mode} | "
            f"{int(Window.width)}x{int(Window.height)} | "
            f"DPI {Window.dpi:.0f}"
        )

    # -------------------------------------------------------------
    # Open AI from any screen
    # -------------------------------------------------------------
    def open_global_ai(self, instance=None):
        manager = self.screen_manager

        if manager is None:
            return

        if manager.current == "ai":
            return

        previous_screen = manager.current

        try:
            ai_screen = manager.get_screen("ai")
            # Save where the user came from.
            ai_screen.return_screen = previous_screen
        except Exception as error:
            log.error(f"Unable to prepare AI screen: {error}")

        manager.current = "ai"

    # -------------------------------------------------------------
    # Open Brainstorm from any screen
    # -------------------------------------------------------------
    def open_global_brainstorm(self, instance=None):
        manager = self.screen_manager

        if manager is None:
            return

        if manager.current == "brainstorm":
            return

        previous_screen = manager.current

        try:
            brainstorm_screen = manager.get_screen("brainstorm")
            brainstorm_screen.return_screen = previous_screen
        except Exception as error:
            log.error(f"Unable to prepare Brainstorm screen: {error}")

        manager.current = "brainstorm"

    # -------------------------------------------------------------
    # Stop services
    # -------------------------------------------------------------
    def on_stop(self):
        if IS_LINUX:
            try:
                Window.unbind(on_key_down=self.on_window_key_down)
                Window.unbind(size=self.on_window_size)
            except Exception:
                pass

        if hasattr(self, "event_notifier"):
            self.event_notifier.stop()

        if hasattr(self, "alarm_notifier"):
            self.alarm_notifier.stop()


if __name__ == "__main__":
    M12OS().run()