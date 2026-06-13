from pathlib import Path
import subprocess

from kivy.utils import platform
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout

from config.version import version_text
from utils.config_manager import ConfigManager
from utils.logger import log
from utils.ui_scale import font, height


BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "logs" / "m12_os.log"
COPY_FILE = BASE_DIR / "logs" / "copied_log_text.txt"


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.config = ConfigManager()
        self.clear_log_pending = False
        self.selected_log_line = ""
        self.log_lines = []

        self.build_settings_view()

    def clear_screen(self):
        self.clear_widgets()

    def make_label(self, text):
        return Label(
            text=text,
            font_size=font(22),
            size_hint=(1, 0.06)
        )

    def make_button(self, text, color=(0.12, 0.20, 0.35, 1)):
        return Button(
            text=text,
            font_size=font(28),
            size_hint=(1, 0.11),
            background_normal="",
            background_color=color
        )

    def build_settings_view(self, instance=None):
        self.clear_screen()
        self.config = ConfigManager()

        root = BoxLayout(orientation="vertical", padding=15, spacing=10)

        root.add_widget(Label(
            text="Settings",
            font_size=font(40),
            bold=True,
            size_hint=(1, 0.12)
        ))

        root.add_widget(Label(
            text=version_text(),
            font_size=font(26),
            size_hint=(1, 0.07)
        ))

        root.add_widget(self.make_label("Temperature Unit"))

        self.unit_spinner = Spinner(
            text=self.config.get("temperature_unit", "F"),
            values=("F", "C"),
            font_size=font(28),
            size_hint=(1, 0.11),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        self.unit_spinner.bind(text=self.change_unit)
        root.add_widget(self.unit_spinner)

        self.auto_btn = self.make_button(
            self.auto_update_text(),
            (0.10, 0.15, 0.25, 1)
        )
        self.auto_btn.bind(on_press=self.toggle_auto_update)
        root.add_widget(self.auto_btn)

        updater_btn = self.make_button("Open Updater")
        updater_btn.bind(on_press=self.open_updater)
        root.add_widget(updater_btn)

        log_btn = self.make_button("View Log")
        log_btn.bind(on_press=self.build_log_view)
        root.add_widget(log_btn)

        back_btn = self.make_button("< Back", (0.10, 0.15, 0.25, 1))
        back_btn.bind(on_press=self.go_back)
        root.add_widget(back_btn)

        self.add_widget(root)

    def build_log_view(self, instance=None):
        self.clear_screen()

        root = BoxLayout(orientation="vertical", padding=10, spacing=6)

        root.add_widget(Label(
            text="M12 OS Log",
            font_size=font(40),
            bold=True,
            size_hint=(1, 0.08)
        ))

        self.log_status = Label(
            text="Tap a line, then Copy Line.",
            font_size=font(20),
            size_hint=(1, 0.09),
            halign="left",
            valign="middle"
        )
        self.log_status.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        root.add_widget(self.log_status)

        buttons1 = BoxLayout(orientation="horizontal", spacing=6, size_hint=(1, 0.08))

        refresh_btn = Button(
            text="Refresh",
            font_size=font(24),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        refresh_btn.bind(on_press=self.refresh_log)
        buttons1.add_widget(refresh_btn)

        copy_line_btn = Button(
            text="Copy Line",
            font_size=font(24),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        copy_line_btn.bind(on_press=self.copy_selected_log_line)
        buttons1.add_widget(copy_line_btn)

        copy_all_btn = Button(
            text="Copy All",
            font_size=font(24),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        copy_all_btn.bind(on_press=self.copy_all_log)
        buttons1.add_widget(copy_all_btn)

        root.add_widget(buttons1)

        buttons2 = BoxLayout(orientation="horizontal", spacing=6, size_hint=(1, 0.08))

        clear_btn = Button(
            text="Clear Log",
            font_size=font(24),
            background_normal="",
            background_color=(0.35, 0.12, 0.12, 1)
        )
        clear_btn.bind(on_press=self.clear_log_confirm)
        buttons2.add_widget(clear_btn)

        back_settings_btn = Button(
            text="< Settings",
            font_size=font(24),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        back_settings_btn.bind(on_press=self.build_settings_view)
        buttons2.add_widget(back_settings_btn)

        home_btn = Button(
            text="< Home",
            font_size=font(24),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        home_btn.bind(on_press=self.go_back)
        buttons2.add_widget(home_btn)

        root.add_widget(buttons2)

        self.log_scroll = ScrollView(size_hint=(1, 0.65), do_scroll_x=False, do_scroll_y=True)

        self.log_list = GridLayout(cols=1, spacing=4, size_hint_y=None)
        self.log_list.bind(minimum_height=self.log_list.setter("height"))

        self.log_scroll.add_widget(self.log_list)
        root.add_widget(self.log_scroll)

        self.add_widget(root)

        self.clear_log_pending = False
        self.load_log_lines()

    def auto_update_text(self):
        return "Auto update check: ON" if self.config.get("auto_update", True) else "Auto update check: OFF"

    def change_unit(self, instance, value):
        self.config.set("temperature_unit", value)
        self.config.set("last_temperature", 22 if value == "C" else 72)

        log.info(f"Settings: temperature_unit={value}")

        if self.manager and self.manager.has_screen("home"):
            home = self.manager.get_screen("home")
            if hasattr(home, "refresh_weather_card"):
                home.refresh_weather_card()

    def toggle_auto_update(self, instance):
        new_value = not self.config.get("auto_update", True)
        self.config.set("auto_update", new_value)
        self.auto_btn.text = self.auto_update_text()
        log.info(f"Settings: auto_update={new_value}")

    def open_updater(self, instance):
        self.manager.current = "updater"

    def read_log_lines(self):
        if not LOG_FILE.exists():
            return [f"No log found: {LOG_FILE}"]

        try:
            text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return [f"Could not read log: {e}"]

        lines = text.splitlines()

        if len(lines) > 500:
            lines = lines[-500:]

        return lines

    def load_log_lines(self):
        self.selected_log_line = ""
        self.log_lines = self.read_log_lines()
        self.log_list.clear_widgets()

        for idx, line in enumerate(self.log_lines, start=1):
            self.add_log_line(idx, line)

        self.log_status.text = f"Lines: {len(self.log_lines)} | Tap a line, then Copy Line."
        self.log_scroll.scroll_y = 0

    def add_log_line(self, idx, line):
        display = line
        if len(display) > 320:
            display = display[:317] + "..."

        btn = Button(
            text=f"{idx}: {display}",
            font_size=font(18),
            size_hint_y=None,
            height=height(70),
            halign="left",
            valign="middle",
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        btn.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - 18, val[1])))
        btn.bind(on_press=lambda instance, text=line: self.select_log_line(text))
        self.log_list.add_widget(btn)

    def select_log_line(self, line):
        self.selected_log_line = line
        self.clear_log_pending = False

        short = line
        if len(short) > 120:
            short = short[:117] + "..."

        self.log_status.text = f"Selected: {short}"

    def refresh_log(self, instance):
        self.clear_log_pending = False
        self.load_log_lines()

    def copy_selected_log_line(self, instance):
        if not self.selected_log_line:
            self.log_status.text = "Select a line first."
            return

        self.safe_copy_text(self.selected_log_line, "Selected line copied.")

    def copy_all_log(self, instance):
        if not self.log_lines:
            self.log_status.text = "No log lines."
            return

        self.safe_copy_text("\n".join(self.log_lines), "All visible log lines copied.")

    def safe_copy_text(self, text, success_message):
        copied = False

        if platform == "macosx":
            try:
                subprocess.run(
                    ["pbcopy"],
                    input=text.encode("utf-8"),
                    check=True
                )
                copied = True
            except Exception as e:
                log.error(f"pbcopy failed: {e}")

        elif platform == "win":
            try:
                subprocess.run(
                    ["clip"],
                    input=text.encode("utf-16le"),
                    check=True
                )
                copied = True
            except Exception as e:
                log.error(f"clip failed: {e}")

        if copied:
            self.log_status.text = success_message
            log.info("Settings: log text copied")
            return

        try:
            COPY_FILE.parent.mkdir(parents=True, exist_ok=True)
            COPY_FILE.write_text(text, encoding="utf-8")
            self.log_status.text = f"Clipboard unavailable. Saved to: {COPY_FILE}"
            log.info(f"Settings: copied text saved to {COPY_FILE}")
        except Exception as e:
            self.log_status.text = f"Copy failed: {e}"
            log.error(f"Settings copy failed: {e}")

    def clear_log_confirm(self, instance):
        if not self.clear_log_pending:
            self.clear_log_pending = True
            self.log_status.text = "Press Clear Log again to erase log file."
            return

        self.clear_log_now()

    def clear_log_now(self):
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            LOG_FILE.write_text("", encoding="utf-8")
            self.clear_log_pending = False
            log.info("Settings: log cleared")
            self.load_log_lines()
            self.log_status.text = "Log cleared."
        except Exception as e:
            self.log_status.text = f"Clear log failed: {e}"
            log.error(f"Settings clear log failed: {e}")

    def go_back(self, instance):
        if self.manager and self.manager.has_screen("home"):
            home = self.manager.get_screen("home")
            if hasattr(home, "refresh_weather_card"):
                home.refresh_weather_card()

        self.manager.current = "home"