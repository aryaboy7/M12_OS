from datetime import datetime

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from utils.ui_scale import font, height

from utils.logger import log


class HomeScreen(Screen):

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

    def open_app(self, instance):
        log.info(f"Button pressed: {instance.text}")

        if "Notes" in instance.text:
            self.manager.current = "notes"
        elif "Clock" in instance.text:
            self.manager.current = "clock"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        root = BoxLayout(orientation="vertical", padding=15, spacing=15)

        clock_card = BoxLayout(orientation="vertical", size_hint=(1, 0.22))

        self.clock_label = Label(text="00:00", font_size=font(60), bold=True)
        self.date_label = Label(text="Date", font_size=font(24))

        clock_card.add_widget(self.clock_label)
        clock_card.add_widget(self.date_label)
        root.add_widget(clock_card)

        weather_card = Button(
            text="🌤  Brooklyn, NY\n72°F Sunny",
            font_size=font(28),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
            size_hint=(1, 0.18)
        )
        root.add_widget(weather_card)

        grid = GridLayout(cols=self.get_columns(), spacing=12, size_hint=(1, 0.60))

        apps = [
            "📝 Notes",
            "🎨 Drawing",
            "📁 Files",
            "🎵 Music",
            "🤖 AI",
            "☁ Weather",
            "🕒 Clock",
            "⚙ Settings"
        ]

        for app in apps:
            btn = Button(
                text=app,
                font_size=font(24),
                background_normal="",
                background_color=(0.10, 0.15, 0.25, 1)
            )
            btn.bind(on_press=self.open_app)
            grid.add_widget(btn)

        root.add_widget(grid)
        self.add_widget(root)