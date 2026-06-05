from datetime import datetime

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from config.version import version_text
from utils.config_manager import ConfigManager
from utils.logger import log
from utils.ui_scale import font


class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = ConfigManager()

        root = BoxLayout(orientation="vertical", padding=15, spacing=15)

        clock_card = BoxLayout(orientation="vertical", size_hint=(1, 0.20))

        self.clock_label = Label(text="00:00", font_size=font(60), bold=True)
        self.date_label = Label(text="Date", font_size=font(24))

        clock_card.add_widget(self.clock_label)
        clock_card.add_widget(self.date_label)
        root.add_widget(clock_card)

        city = self.config.get("city", "Brooklyn, NY")
        unit = self.config.get("temperature_unit", "F")
        weather_card = Button(
            text=f"🌤  {city}\nWeather app  |  °{unit}",
            font_size=font(26),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
            size_hint=(1, 0.16)
        )
        weather_card.bind(on_press=lambda instance: self.open_screen("weather"))
        root.add_widget(weather_card)

        grid = GridLayout(cols=self.get_columns(), spacing=12, size_hint=(1, 0.56))

        apps = [
            ("📝 Notes", "notes"),
            ("🎨 Drawing", "drawing"),
            ("📁 Files", "files"),
            ("🎵 Music", "music"),
            ("🤖 AI", "ai"),
            ("☁ Weather", "weather"),
            ("🕒 Clock", "clock"),
            ("⚙ Settings", "settings"),
            ("⬆ Updater", "updater")
        ]

        for title, screen_name in apps:
            btn = Button(
                text=title,
                font_size=font(23),
                background_normal="",
                background_color=(0.10, 0.15, 0.25, 1)
            )
            btn.bind(on_press=lambda instance, name=screen_name: self.open_screen(name))
            grid.add_widget(btn)

        root.add_widget(grid)

        self.version_label = Label(
            text=version_text(),
            font_size=font(16),
            size_hint=(1, 0.06)
        )
        root.add_widget(self.version_label)

        self.add_widget(root)

    def on_enter(self):
        Clock.schedule_interval(self.update_time, 1)
        self.update_time(0)

    def on_leave(self):
        Clock.unschedule(self.update_time)

    def update_time(self, dt):
        self.clock_label.text = datetime.now().strftime("%I:%M %p")
        self.date_label.text = datetime.now().strftime("%A, %B %d")

    def get_columns(self):
        if Window.width < 700:
            return 2
        elif Window.width < 1200:
            return 3
        return 4

    def open_screen(self, screen_name):
        log.info(f"Home: open {screen_name}")
        if self.manager and self.manager.has_screen(screen_name):
            self.manager.current = screen_name
        else:
            log.error(f"Home: missing screen {screen_name}")
