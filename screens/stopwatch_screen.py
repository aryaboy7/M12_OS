from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from utils.logger import log
from utils.ui_scale import (
    device_profile,
    button_font,
    text_font,
    clock_time_font,
    button_height,
    padding_size,
    spacing_size,
)


def stopwatch_time_font():
    profile = device_profile()

    if profile == "phone":
        return 118
    if profile == "tablet":
        return 86
    if profile == "m12":
        return 68

    return clock_time_font()


class StopwatchScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.running = False
        self.elapsed = 0.0

        root = BoxLayout(
            orientation="vertical",
            spacing=spacing_size(),
            padding=padding_size(),
        )

        self.time_label = Label(
            text="00:00.00",
            font_size=stopwatch_time_font(),
            bold=True,
            size_hint=(1, 0.62),
            halign="center",
            valign="middle",
        )
        root.add_widget(self.time_label)

        controls = BoxLayout(
            spacing=spacing_size(),
            size_hint=(1, 0.23),
        )

        self.start_btn = Button(
            text="Start",
            font_size=button_font(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
        )
        self.start_btn.bind(on_press=self.start_stop)

        reset_btn = Button(
            text="Reset",
            font_size=button_font(),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1),
        )
        reset_btn.bind(on_press=self.reset)

        back_btn = Button(
            text="< Back",
            font_size=button_font(),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1),
        )
        back_btn.bind(on_press=self.go_back)

        controls.add_widget(self.start_btn)
        controls.add_widget(reset_btn)
        controls.add_widget(back_btn)

        root.add_widget(controls)

        self.info_label = Label(
            text="Stopwatch",
            font_size=text_font(),
            size_hint=(1, 0.10),
            halign="center",
            valign="middle",
        )
        root.add_widget(self.info_label)

        self.add_widget(root)

    def on_enter(self):
        log.info("Stopwatch: opened")
        Clock.unschedule(self.update)
        Clock.schedule_interval(self.update, 0.05)
        self.update(0)

    def on_leave(self):
        Clock.unschedule(self.update)

    def update(self, dt):
        if self.running:
            self.elapsed += dt

        minutes = int(self.elapsed // 60)
        seconds = int(self.elapsed % 60)
        hundredths = int((self.elapsed - int(self.elapsed)) * 100)

        self.time_label.text = f"{minutes:02}:{seconds:02}.{hundredths:02}"

    def start_stop(self, instance):
        self.running = not self.running
        self.start_btn.text = "Stop" if self.running else "Start"
        log.info(f"Stopwatch: {'started' if self.running else 'stopped'}")

    def reset(self, instance):
        self.running = False
        self.elapsed = 0.0
        self.start_btn.text = "Start"
        self.update(0)
        log.info("Stopwatch: reset")

    def go_back(self, instance):
        self.manager.current = "clock"
