from datetime import datetime
from logging import root

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from utils.ui_scale import font, height

from utils.logger import log


class ClockScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        root = BoxLayout(
            orientation="vertical",
            spacing=12,
            padding=15
        )

        top = BoxLayout(size_hint=(1, 0.12))

        back_btn = Button(
            text="< Back",
            font_size=font(22),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        back_btn.bind(on_press=self.go_back)

        top.add_widget(back_btn)
        root.add_widget(top)

        self.time_label = Label(
            text="00:00:00",
            font_size=font(78),
            bold=True,
            size_hint=(1, 0.45)
        )
        root.add_widget(self.time_label)

        self.date_label = Label(
            text="Date",
            font_size=font(39),
            size_hint=(1, 0.20)
        )
        root.add_widget(self.date_label)

        timer_btn = Button(
            text="Timer",
            font_size=font(26),
            size_hint=(1, 0.15),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
)
        timer_btn.bind(on_press=self.open_timer)
        root.add_widget(timer_btn)

        stopwatch_btn = Button(
            text="Stopwatch",
            font_size=font(26),
            size_hint=(1, 0.15),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
    )
        stopwatch_btn.bind(on_press=self.open_stopwatch)
        root.add_widget(stopwatch_btn)

        self.info_label = Label(
            text="M12 Clock",
            font_size=font(22),
            size_hint=(1, 0.23)
        )
        root.add_widget(self.info_label)

        self.add_widget(root)

    def on_enter(self):
        log.info("Clock: opened")
        Clock.schedule_interval(self.update_clock, 1)
        self.update_clock(0)

    def on_leave(self):
        Clock.unschedule(self.update_clock)

    def update_clock(self, dt):
        now = datetime.now()
        self.time_label.text = now.strftime("%I:%M:%S %p")
        self.date_label.text = now.strftime("%A, %B %d, %Y")

    def go_back(self, instance):
        log.info("Clock: Back pressed")
        self.manager.current = "home"

    def open_stopwatch(self, instance):
        log.info("Clock: Stopwatch pressed")
        self.manager.current = "stopwatch"

    def open_timer(self, instance):
        log.info("Clock: Timer pressed")
        self.manager.current = "timer"    