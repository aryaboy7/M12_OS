# M12 OS Home Screen - shared UI scale version
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.graphics import Color, Rectangle

from config.version import VERSION
from utils.config_manager import ConfigManager
from utils.logger import log
from utils.ui_scale import (
    device_profile,
    title_font,
    button_font,
    list_font,
    text_font,
    status_font,
    clock_time_font,
    clock_date_font,
    top_bar_height,
    padding_size,
    spacing_size,
)


BASE_DIR = Path(__file__).resolve().parent.parent
EVENTS_FILE = BASE_DIR / "data" / "events" / "events.json"
ALARMS_FILE = BASE_DIR / "data" / "alarms" / "alarms.json"

BG = (0.04, 0.07, 0.12, 1)
CARD_CLOCK = (0.08, 0.18, 0.32, 1)
CARD_WEATHER = (0.08, 0.28, 0.38, 1)
STATUS_BG = (0.06, 0.10, 0.18, 1)

TILE_COLORS = [
    (0.13, 0.28, 0.48, 1),
    (0.16, 0.34, 0.28, 1),
    (0.34, 0.22, 0.46, 1),
    (0.42, 0.28, 0.12, 1),
    (0.36, 0.16, 0.18, 1),
    (0.14, 0.32, 0.42, 1),
]





class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.config = ConfigManager()
        self.app_buttons = {}

        profile = device_profile()

        padding = padding_size()
        spacing = spacing_size()

        if profile == "phone":
            status_hint = 0.055
            clock_hint = 0.17
            weather_hint = 0.15
            grid_hint = 0.575
            version_hint = 0.04
        elif profile in ("tablet", "m12"):
            status_hint = 0.055
            clock_hint = 0.16
            weather_hint = 0.14
            grid_hint = 0.60
            version_hint = 0.04
        else:
            status_hint = 0.06
            clock_hint = 0.16
            weather_hint = 0.14
            grid_hint = 0.58
            version_hint = 0.04

        self.app_size = button_font()

        root = BoxLayout(orientation="vertical", padding=padding, spacing=spacing)

        with root.canvas.before:
            Color(*BG)
            self.bg_rect = Rectangle(pos=root.pos, size=root.size)

        root.bind(pos=self.update_bg, size=self.update_bg)

        status_bar = BoxLayout(
            orientation="horizontal",
            size_hint=(1, status_hint),
            spacing=spacing_size(),
            padding=(spacing_size(), 2)
        )

        with status_bar.canvas.before:
            Color(*STATUS_BG)
            self.status_rect = Rectangle(pos=status_bar.pos, size=status_bar.size)

        status_bar.bind(pos=self.update_status_bg, size=self.update_status_bg)

        self.status_left = Label(
            text=f"M12 OS {VERSION}",
            font_size=status_font(),
            color=(0.75, 0.85, 1, 1),
            halign="left",
            valign="middle",
            size_hint=(0.35, 1)
        )

        self.status_center = Label(
            text="WiFi: OK",
            font_size=status_font(),
            color=(0.75, 1, 0.80, 1),
            halign="center",
            valign="middle",
            size_hint=(0.40, 1)
        )

        self.status_time = Label(
            text="--:--:--",
            font_size=status_font(),
            color=(1, 1, 1, 1),
            halign="right",
            valign="middle",
            size_hint=(0.25, 1)
        )

        self.status_left.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.status_center.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.status_time.bind(size=lambda inst, val: setattr(inst, "text_size", val))

        status_bar.add_widget(self.status_left)
        status_bar.add_widget(self.status_center)
        status_bar.add_widget(self.status_time)
        root.add_widget(status_bar)

        clock_card = BoxLayout(
            orientation="vertical",
            size_hint=(1, clock_hint),
            padding=spacing_size()
        )

        with clock_card.canvas.before:
            Color(*CARD_CLOCK)
            self.clock_rect = Rectangle(pos=clock_card.pos, size=clock_card.size)

        clock_card.bind(pos=self.update_clock_bg, size=self.update_clock_bg)

        self.clock_label = Label(
            text="00:00",
            font_size=clock_time_font(),
            bold=True,
            color=(1, 1, 1, 1)
        )

        self.date_label = Label(
            text="Date",
            font_size=clock_date_font(),
            color=(0.75, 0.88, 1, 1)
        )

        clock_card.add_widget(self.clock_label)
        clock_card.add_widget(self.date_label)
        root.add_widget(clock_card)

        city = self.config.get("city", "Brooklyn, NY")
        unit = self.config.get("temperature_unit", "F")

        self.weather_card = Button(
            text=f"Weather\n{city}  °{unit}",
            font_size=text_font(),
            background_normal="",
            background_color=CARD_WEATHER,
            color=(1, 1, 1, 1),
            size_hint=(1, weather_hint),
            halign="center",
            valign="middle",
            bold=True
        )
        self.weather_card.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.weather_card.bind(on_press=lambda instance: self.open_screen("weather"))
        root.add_widget(self.weather_card)

        self.grid = GridLayout(
            cols=self.get_columns(),
            spacing=spacing,
            size_hint=(1, grid_hint)
        )

        self.apps = [
            ("Notes", "notes"),
            ("Drawing", "drawing"),
            ("Calendar", "calendar"),
            ("Files", "files"),
            ("Music", "music"),
            ("AI", "ai"),
            ("Weather", "weather"),
            ("Clock", "clock"),
            ("Calculator", "calculator"),
            ("Settings", "settings"),
            ("Updater", "updater"),
            ("Restart", "restart"),
        ]

        self.build_app_buttons()
        root.add_widget(self.grid)

        self.version_label = Label(
            text=f"M12 OS {VERSION}",
            font_size=status_font(),
            size_hint=(1, version_hint),
            color=(0.65, 0.75, 0.90, 1)
        )
        root.add_widget(self.version_label)

        self.add_widget(root)

    def build_app_buttons(self):
        self.grid.clear_widgets()
        self.app_buttons = {}

        today_count = self.get_today_calendar_count()
        alarm_active = self.is_alarm_active()

        for index, (title, screen_name) in enumerate(self.apps):
            display_title = title

            if title == "Calendar" and today_count > 0:
                display_title = f"Calendar ({today_count})"

            if title == "Clock" and alarm_active:
                display_title = "Clock (AL)"

            btn = Button(
                text=display_title,
                font_size=button_font(),
                background_normal="",
                background_color=TILE_COLORS[index % len(TILE_COLORS)],
                color=(1, 1, 1, 1),
                halign="center",
                valign="middle",
                bold=True
            )

            btn.bind(size=lambda inst, val: setattr(inst, "text_size", val))
            btn.bind(on_press=lambda instance, name=screen_name: self.open_screen(name))

            self.grid.add_widget(btn)
            self.app_buttons[screen_name] = btn

        remainder = len(self.apps) % self.get_columns()
        if remainder != 0:
            missing = self.get_columns() - remainder
            for _ in range(missing):
                self.grid.add_widget(Button(
                    text="",
                    disabled=True,
                    background_normal="",
                    background_color=(0, 0, 0, 0)
                ))

    def is_alarm_active(self):
        try:
            if not ALARMS_FILE.exists():
                return False

            alarms = json.loads(ALARMS_FILE.read_text(encoding="utf-8"))

            if not isinstance(alarms, list):
                return False

            for alarm in alarms:
                if alarm.get("enabled", False):
                    return True

            return False

        except Exception as e:
            log.error(f"Home: alarm active check failed {e}")
            return False

    def refresh_clock_button(self):
        btn = self.app_buttons.get("clock")

        if not btn:
            return

        if self.is_alarm_active():
            btn.text = "Clock (AL)"
        else:
            btn.text = "Clock"

    def parse_event_datetime(self, event):
        try:
            date_text = str(event.get("date", "")).strip()
            time_text = str(event.get("time", "")).strip() or "00:00"
            return datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")
        except Exception:
            return None

    def get_today_occurrence_for_home(self, event, now):
        base_dt = self.parse_event_datetime(event)

        if not base_dt:
            return None

        repeat_mode = event.get("repeat_mode", "once")
        today = now.date()

        if repeat_mode == "once":
            return base_dt

        if today < base_dt.date():
            return None

        until_date = str(event.get("until_date", "")).strip()

        if until_date:
            try:
                until = datetime.strptime(until_date, "%Y-%m-%d").date()
                if today > until:
                    return None
            except Exception:
                pass

        if repeat_mode == "every_day":
            return datetime.combine(today, base_dt.time())

        if repeat_mode == "days":
            today_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][today.weekday()]
            days = event.get("days", [])

            if today_name in days:
                return datetime.combine(today, base_dt.time())

        return None

    def get_today_calendar_count(self):
        try:
            if not EVENTS_FILE.exists():
                return 0

            events = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))

            if not isinstance(events, list):
                return 0

            now = datetime.now()
            today = now.date()
            count = 0

            for event in events:
                occurrence = self.get_today_occurrence_for_home(event, now)

                if not occurrence:
                    continue

                if occurrence.date() == today and occurrence >= now:
                    count += 1

            return count

        except Exception as e:
            log.error(f"Home: today calendar count failed {e}")
            return 0

    def refresh_calendar_button(self):
        btn = self.app_buttons.get("calendar")

        if not btn:
            return

        count = self.get_today_calendar_count()
        btn.text = f"Calendar ({count})" if count > 0 else "Calendar"

    def update_bg(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size

    def update_status_bg(self, instance, value):
        self.status_rect.pos = instance.pos
        self.status_rect.size = instance.size

    def update_clock_bg(self, instance, value):
        self.clock_rect.pos = instance.pos
        self.clock_rect.size = instance.size

    def on_enter(self):
        self.config = ConfigManager()
        self.refresh_weather_card()
        self.refresh_calendar_button()
        self.refresh_clock_button()

        Clock.unschedule(self.update_time)
        Clock.schedule_interval(self.update_time, 1)
        self.update_time(0)

    def refresh_weather_card(self):
        self.config = ConfigManager()

        city = self.config.get("city", "Brooklyn, NY")
        unit = self.config.get("temperature_unit", "F")
        temp = self.config.get("last_temperature", "--")
        condition = self.config.get("last_condition", "")

        if condition:
            self.weather_card.text = f"Weather\n{city}\n{temp}°{unit}  {condition}"
        else:
            self.weather_card.text = f"Weather\n{city}\n{temp}°{unit}"

    def on_leave(self):
        Clock.unschedule(self.update_time)

    def update_time(self, dt):
        now = datetime.now()
        self.clock_label.text = now.strftime("%I:%M %p")
        self.date_label.text = now.strftime("%A, %B %d")
        self.status_time.text = now.strftime("%H:%M:%S")

    def get_columns(self):
        profile = device_profile()

        if profile in ("phone", "m12", "tablet"):
            return 2

        return 5

    def restart_app(self):
        log.info("Home: restarting app")

        app = App.get_running_app()

        if app:
            app.stop()

        os.execv(sys.executable, [sys.executable] + sys.argv)

    def open_screen(self, screen_name):
        log.info(f"Home: open {screen_name}")

        if screen_name == "restart":
            self.restart_app()
            return

        if self.manager and self.manager.has_screen(screen_name):
            self.manager.current = screen_name
        else:
            log.error(f"Home: missing screen {screen_name}")
