from datetime import datetime

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from config.version import VERSION
from utils.config_manager import ConfigManager
from utils.logger import log


def device_profile():
    w = Window.width
    h = Window.height

    if h >= 1800:
        return "phone"

    if w < 700 and h >= 900:
        return "m12"

    if h >= 1100:
        return "tablet"

    return "desktop"


def home_font(base):
    profile = device_profile()

    if profile == "phone":
        scale = 1.85
    elif profile == "tablet":
        scale = 1.45
    elif profile == "m12":
        scale = 1.35
    else:
        scale = 1.00

    return max(14, int(base * scale))


class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.config = ConfigManager()

        profile = device_profile()

        if profile == "phone":
            padding = 22
            spacing = 22
        elif profile in ("tablet", "m12"):
            padding = 16
            spacing = 14
        else:
            padding = 15
            spacing = 15

        root = BoxLayout(
            orientation="vertical",
            padding=padding,
            spacing=spacing
        )

        if profile == "phone":
            clock_hint = 0.19
            weather_hint = 0.15
            grid_hint = 0.56
            version_hint = 0.06
            clock_size = 52
            date_size = 23
            weather_size = 23
            app_size = 21
            version_size = 13
        elif profile == "tablet":
            clock_hint = 0.19
            weather_hint = 0.15
            grid_hint = 0.56
            version_hint = 0.06
            clock_size = 50
            date_size = 22
            weather_size = 22
            app_size = 20
            version_size = 13
        elif profile == "m12":
            clock_hint = 0.18
            weather_hint = 0.14
            grid_hint = 0.58
            version_hint = 0.06
            clock_size = 40
            date_size = 18
            weather_size = 18
            app_size = 17
            version_size = 11
        else:
            clock_hint = 0.20
            weather_hint = 0.16
            grid_hint = 0.56
            version_hint = 0.06
            clock_size = 60
            date_size = 24
            weather_size = 26
            app_size = 23
            version_size = 14

        clock_card = BoxLayout(
            orientation="vertical",
            size_hint=(1, clock_hint)
        )

        self.clock_label = Label(
            text="00:00",
            font_size=home_font(clock_size),
            bold=True,
            halign="center",
            valign="middle"
        )

        self.date_label = Label(
            text="Date",
            font_size=home_font(date_size),
            halign="center",
            valign="middle"
        )

        clock_card.add_widget(self.clock_label)
        clock_card.add_widget(self.date_label)
        root.add_widget(clock_card)

        city = self.config.get("city", "Brooklyn, NY")
        unit = self.config.get("temperature_unit", "F")

        self.weather_card = Button(
            text=f"Weather\n{city}  °{unit}",
            font_size=home_font(weather_size),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
            size_hint=(1, weather_hint),
            halign="center",
            valign="middle"
        )
        self.weather_card.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.weather_card.bind(on_press=lambda instance: self.open_screen("weather"))
        root.add_widget(self.weather_card)

        grid = GridLayout(
            cols=self.get_columns(),
            spacing=spacing,
            size_hint=(1, grid_hint)
        )

        apps = [
            ("Notes", "notes"),
            ("Drawing", "drawing"),
            ("Files", "files"),
            ("Music", "music"),
            ("AI", "ai"),
            ("Weather", "weather"),
            ("Clock", "clock"),
            ("Settings", "settings"),
            ("Updater", "updater")
        ]

        for title, screen_name in apps:
            btn = Button(
                text=title,
                font_size=home_font(app_size),
                background_normal="",
                background_color=(0.10, 0.15, 0.25, 1),
                halign="center",
                valign="middle"
            )
            btn.bind(size=lambda inst, val: setattr(inst, "text_size", val))
            btn.bind(on_press=lambda instance, name=screen_name: self.open_screen(name))
            grid.add_widget(btn)

        root.add_widget(grid)

        self.version_label = Label(
            text=f"M12 OS {VERSION}",
            font_size=home_font(version_size),
            size_hint=(1, version_hint),
            halign="center",
            valign="middle"
        )
        root.add_widget(self.version_label)

        self.add_widget(root)

    def on_enter(self):
        self.config = ConfigManager()
        self.refresh_weather_card()

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
            self.weather_card.text = (
                f"Weather\n"
                f"{city}\n"
                f"{temp}°{unit}  {condition}"
            )
        else:
            self.weather_card.text = (
                f"Weather\n"
                f"{city}\n"
                f"{temp}°{unit}"
            )

    def on_leave(self):
        Clock.unschedule(self.update_time)

    def update_time(self, dt):
        self.clock_label.text = datetime.now().strftime("%I:%M %p")
        self.date_label.text = datetime.now().strftime("%A, %B %d")

    def get_columns(self):
        profile = device_profile()

        if profile == "phone":
            return 2

        if profile == "m12":
            return 2

        if profile == "tablet":
            return 3

        if Window.width < 1200:
            return 3

        return 4

    def open_screen(self, screen_name):
        log.info(f"Home: open {screen_name}")

        if self.manager and self.manager.has_screen(screen_name):
            self.manager.current = screen_name
        else:
            log.error(f"Home: missing screen {screen_name}")
