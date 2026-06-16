from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from utils.logger import log
from utils.ui_scale import (
    device_profile,
    title_font,
    button_font,
    text_font,
    status_font,
    clock_time_font,
    button_height,
    padding_size,
    spacing_size,
    height,
)


def wheel_title_font():
    profile = device_profile()

    if profile == "phone":
        return 42
    if profile == "tablet":
        return 30
    if profile == "m12":
        return 24

    return text_font()


def wheel_side_font():
    profile = device_profile()

    if profile == "phone":
        return 44
    if profile == "tablet":
        return 32
    if profile == "m12":
        return 26

    return text_font()


def wheel_value_font():
    profile = device_profile()

    if profile == "phone":
        return 86
    if profile == "tablet":
        return 62
    if profile == "m12":
        return 48

    return clock_time_font()


def timer_time_font():
    profile = device_profile()

    if profile == "phone":
        return 96
    if profile == "tablet":
        return 72
    if profile == "m12":
        return 58

    return clock_time_font()


class NumberWheel(BoxLayout):
    def __init__(self, title, value=0, minimum=0, maximum=59, **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=spacing_size(),
            **kwargs
        )

        self.title = title
        self.value = value
        self.minimum = minimum
        self.maximum = maximum
        self.start_y = 0

        self.add_widget(Label(
            text=title,
            font_size=wheel_title_font(),
            size_hint=(1, 0.18),
        ))

        self.up_label = Label(
            text="",
            font_size=wheel_side_font(),
            size_hint=(1, 0.22),
        )

        self.value_label = Label(
            text="",
            font_size=wheel_value_font(),
            bold=True,
            size_hint=(1, 0.38),
        )

        self.down_label = Label(
            text="",
            font_size=wheel_side_font(),
            size_hint=(1, 0.22),
        )

        self.add_widget(self.up_label)
        self.add_widget(self.value_label)
        self.add_widget(self.down_label)

        self.update_labels()

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.start_y = touch.y
            return True

        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            diff = touch.y - self.start_y

            if diff > height(25):
                self.change(1)
            elif diff < -height(25):
                self.change(-1)

            return True

        return super().on_touch_up(touch)

    def change(self, delta):
        self.value += delta

        if self.value > self.maximum:
            self.value = self.minimum

        if self.value < self.minimum:
            self.value = self.maximum

        self.update_labels()

    def update_labels(self):
        up = self.value + 1
        down = self.value - 1

        if up > self.maximum:
            up = self.minimum

        if down < self.minimum:
            down = self.maximum

        self.up_label.text = f"{up:02}"
        self.value_label.text = f"{self.value:02}"
        self.down_label.text = f"{down:02}"


class TimerScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.running = False
        self.remaining = 0
        self.original_seconds = 0

        root = BoxLayout(
            orientation="vertical",
            spacing=spacing_size(),
            padding=padding_size(),
        )

        title = Label(
            text="Timer",
            font_size=title_font(),
            bold=True,
            size_hint=(1, 0.09),
        )
        root.add_widget(title)

        wheels = BoxLayout(
            spacing=spacing_size(),
            size_hint=(1, 0.36),
        )

        self.hours_wheel = NumberWheel("Hours", value=0, minimum=0, maximum=23)
        self.minutes_wheel = NumberWheel("Minutes", value=5, minimum=0, maximum=59)
        self.seconds_wheel = NumberWheel("Seconds", value=0, minimum=0, maximum=59)

        wheels.add_widget(self.hours_wheel)
        wheels.add_widget(self.minutes_wheel)
        wheels.add_widget(self.seconds_wheel)

        root.add_widget(wheels)

        self.time_label = Label(
            text="00:05:00",
            font_size=timer_time_font(),
            bold=True,
            size_hint=(1, 0.20),
        )
        root.add_widget(self.time_label)

        self.status_label = Label(
            text="Swipe wheels up/down to set time",
            font_size=status_font(),
            size_hint=(1, 0.10),
        )
        root.add_widget(self.status_label)

        controls = BoxLayout(
            spacing=spacing_size(),
            size_hint=(1, 0.15),
        )

        start_btn = Button(
            text="Start",
            font_size=button_font(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
        )
        start_btn.bind(on_press=self.start)

        stop_btn = Button(
            text="Stop",
            font_size=button_font(),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1),
        )
        stop_btn.bind(on_press=self.stop)

        reset_btn = Button(
            text="Reset",
            font_size=button_font(),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1),
        )
        reset_btn.bind(on_press=self.reset)

        controls.add_widget(start_btn)
        controls.add_widget(stop_btn)
        controls.add_widget(reset_btn)

        root.add_widget(controls)

        back_btn = Button(
            text="< Back",
            font_size=button_font(),
            size_hint=(1, None),
            height=button_height(),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1),
        )
        back_btn.bind(on_press=self.go_back)
        root.add_widget(back_btn)

        self.add_widget(root)

    def on_enter(self):
        log.info("Timer: opened")
        Clock.unschedule(self.tick)
        Clock.schedule_interval(self.tick, 1)
        self.update_display()

    def on_leave(self):
        Clock.unschedule(self.tick)

    def read_seconds_from_wheels(self):
        return (
            self.hours_wheel.value * 3600 +
            self.minutes_wheel.value * 60 +
            self.seconds_wheel.value
        )

    def start(self, instance):
        if self.remaining <= 0:
            self.remaining = self.read_seconds_from_wheels()
            self.original_seconds = self.remaining

        if self.remaining <= 0:
            self.status_label.text = "Set time first"
            log.warning("Timer: start pressed with zero time")
            return

        self.running = True
        self.status_label.text = "Running"
        log.info("Timer: started")
        self.update_display()

    def stop(self, instance):
        self.running = False
        self.status_label.text = "Stopped"
        log.info("Timer: stopped")

    def reset(self, instance):
        self.running = False
        self.remaining = self.original_seconds or self.read_seconds_from_wheels()
        self.status_label.text = "Ready"
        log.info("Timer: reset")
        self.update_display()

    def tick(self, dt):
        if not self.running:
            self.update_display()
            return

        if self.remaining > 0:
            self.remaining -= 1

        if self.remaining <= 0:
            self.running = False
            self.remaining = 0
            self.status_label.text = "TIME IS UP!"
            log.info("Timer: time is up")

        self.update_display()

    def update_display(self):
        total = self.remaining if self.remaining > 0 else self.read_seconds_from_wheels()

        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60

        self.time_label.text = f"{h:02}:{m:02}:{s:02}"

    def go_back(self, instance):
        log.info("Timer: Back pressed")
        self.manager.current = "clock"
