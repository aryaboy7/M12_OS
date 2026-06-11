from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from utils.ui_scale import font, height
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


def timer_font(base):
    profile = device_profile()

    if profile == "phone":
        scale = 1.75
    elif profile == "tablet":
        scale = 1.45
    elif profile == "m12":
        scale = 1.30
    else:
        scale = 1.00

    return max(14, int(base * scale))


class NumberWheel(BoxLayout):
    def __init__(self, title, value=0, minimum=0, maximum=59, **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=height(6),
            **kwargs
        )

        self.title = title
        self.value = value
        self.minimum = minimum
        self.maximum = maximum
        self.start_y = 0

        profile = device_profile()

        if profile == "phone":
            title_size = 22
            side_size = 24
            value_size = 52
        elif profile == "tablet":
            title_size = 21
            side_size = 23
            value_size = 48
        elif profile == "m12":
            title_size = 18
            side_size = 20
            value_size = 42
        else:
            title_size = 24
            side_size = 24
            value_size = 48

        self.add_widget(Label(
            text=title,
            font_size=timer_font(title_size),
            size_hint=(1, 0.18)
        ))

        self.up_label = Label(
            text="",
            font_size=timer_font(side_size),
            size_hint=(1, 0.22)
        )

        self.value_label = Label(
            text="",
            font_size=timer_font(value_size),
            bold=True,
            size_hint=(1, 0.38)
        )

        self.down_label = Label(
            text="",
            font_size=timer_font(side_size),
            size_hint=(1, 0.22)
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
            spacing=height(12),
            padding=height(15)
        )

        title = Label(
            text="Timer",
            font_size=timer_font(34),
            bold=True,
            size_hint=(1, 0.09)
        )
        root.add_widget(title)

        wheels = BoxLayout(
            spacing=height(10),
            size_hint=(1, 0.36)
        )

        self.hours_wheel = NumberWheel("Hours", value=0, minimum=0, maximum=23)
        self.minutes_wheel = NumberWheel("Minutes", value=5, minimum=0, maximum=59)
        self.seconds_wheel = NumberWheel("Seconds", value=0, minimum=0, maximum=59)

        wheels.add_widget(self.hours_wheel)
        wheels.add_widget(self.minutes_wheel)
        wheels.add_widget(self.seconds_wheel)

        root.add_widget(wheels)

        profile = device_profile()

        if profile == "phone":
            time_size = 56
            status_size = 22
            button_size = 24
        elif profile == "tablet":
            time_size = 54
            status_size = 22
            button_size = 23
        elif profile == "m12":
            time_size = 48
            status_size = 20
            button_size = 21
        else:
            time_size = 58
            status_size = 22
            button_size = 24

        self.time_label = Label(
            text="00:05:00",
            font_size=timer_font(time_size),
            bold=True,
            size_hint=(1, 0.20)
        )
        root.add_widget(self.time_label)

        self.status_label = Label(
            text="Swipe wheels up/down to set time",
            font_size=timer_font(status_size),
            size_hint=(1, 0.10)
        )
        root.add_widget(self.status_label)

        controls = BoxLayout(
            spacing=height(10),
            size_hint=(1, 0.15)
        )

        start_btn = Button(
            text="Start",
            font_size=timer_font(button_size),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        start_btn.bind(on_press=self.start)

        stop_btn = Button(
            text="Stop",
            font_size=timer_font(button_size),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        stop_btn.bind(on_press=self.stop)

        reset_btn = Button(
            text="Reset",
            font_size=timer_font(button_size),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        reset_btn.bind(on_press=self.reset)

        controls.add_widget(start_btn)
        controls.add_widget(stop_btn)
        controls.add_widget(reset_btn)

        root.add_widget(controls)

        back_btn = Button(
            text="< Back",
            font_size=timer_font(button_size),
            size_hint=(1, 0.09),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
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
