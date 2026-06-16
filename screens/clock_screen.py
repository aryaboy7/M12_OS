import json
from datetime import datetime
from pathlib import Path

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from utils.logger import log
from utils.ui_scale import (
    device_profile,
    button_font,
    text_font,
    status_font,
    clock_time_font,
    clock_date_font,
    button_height,
    padding_size,
    spacing_size,
)


BASE_DIR = Path(__file__).resolve().parent.parent
ALARMS_FILE = BASE_DIR / "data" / "alarms" / "alarms.json"


def alarm_info_font():
    profile = device_profile()

    if profile == "phone":
        return 40
    if profile == "tablet":
        return 28
    if profile == "m12":
        return 22

    return status_font()


def clock_info_font():
    profile = device_profile()

    if profile == "phone":
        return 38
    if profile == "tablet":
        return 28
    if profile == "m12":
        return 22

    return text_font()


class ClockScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.root_box = BoxLayout(
            orientation="vertical",
            spacing=spacing_size(),
            padding=padding_size(),
        )

        top = BoxLayout(
            size_hint=(1, None),
            height=button_height(),
            spacing=spacing_size(),
        )

        self.back_btn = Button(
            text="< Back",
            font_size=button_font(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
        )
        self.back_btn.bind(on_press=self.go_back)

        top.add_widget(self.back_btn)
        self.root_box.add_widget(top)

        self.time_label = Label(
            text="00:00 AM",
            font_size=clock_time_font(),
            bold=True,
            size_hint=(1, 0.34),
            halign="center",
            valign="middle",
        )
        self.root_box.add_widget(self.time_label)

        self.date_label = Label(
            text="Date",
            font_size=clock_date_font(),
            size_hint=(1, 0.13),
            halign="center",
            valign="middle",
        )
        self.root_box.add_widget(self.date_label)

        self.alarm_info_label = Label(
            text="No Alarm",
            font_size=alarm_info_font(),
            size_hint=(1, 0.07),
            color=(0.75, 0.85, 1, 1),
            halign="center",
            valign="middle",
        )
        self.root_box.add_widget(self.alarm_info_label)

        buttons = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, 0.15),
        )

        self.timer_btn = Button(
            text="Timer",
            font_size=button_font(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
        )
        self.timer_btn.bind(on_press=self.open_timer)
        buttons.add_widget(self.timer_btn)

        self.stopwatch_btn = Button(
            text="Stopwatch",
            font_size=button_font(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1),
        )
        self.stopwatch_btn.bind(on_press=self.open_stopwatch)
        buttons.add_widget(self.stopwatch_btn)

        self.alarm_btn = Button(
            text="Alarm",
            font_size=button_font(),
            background_normal="",
            background_color=(0.16, 0.32, 0.42, 1),
        )
        self.alarm_btn.bind(on_press=self.open_alarm)
        buttons.add_widget(self.alarm_btn)

        self.root_box.add_widget(buttons)

        self.info_label = Label(
            text="M12 Clock",
            font_size=clock_info_font(),
            size_hint=(1, 0.10),
            halign="center",
            valign="middle",
        )
        self.root_box.add_widget(self.info_label)

        self.add_widget(self.root_box)

        Window.bind(size=self.on_window_size)

    def on_enter(self):
        log.info("Clock: opened")
        self.apply_layout()
        self.refresh_alarm_info()

        Clock.unschedule(self.update_clock)
        Clock.schedule_interval(self.update_clock, 1)
        self.update_clock(0)

    def on_leave(self):
        Clock.unschedule(self.update_clock)

    def on_window_size(self, *args):
        self.apply_layout()

    def apply_layout(self):
        profile = device_profile()
        portrait = Window.height > Window.width

        self.back_btn.font_size = button_font()
        self.timer_btn.font_size = button_font()
        self.stopwatch_btn.font_size = button_font()
        self.alarm_btn.font_size = button_font()
        self.date_label.font_size = clock_date_font()
        self.alarm_info_label.font_size = alarm_info_font()
        self.info_label.font_size = clock_info_font()

        if portrait:
            if profile == "phone":
                self.time_label.font_size = 118
                self.date_label.font_size = 46
                self.alarm_info_label.font_size = 40
                self.info_label.font_size = 38
                self.time_label.size_hint = (1, 0.36)
                self.date_label.size_hint = (1, 0.13)
                self.alarm_info_label.size_hint = (1, 0.07)

            elif profile == "tablet":
                self.time_label.font_size = 84
                self.date_label.font_size = 34
                self.alarm_info_label.font_size = 28
                self.info_label.font_size = 28
                self.time_label.size_hint = (1, 0.35)
                self.date_label.size_hint = (1, 0.13)
                self.alarm_info_label.size_hint = (1, 0.07)

            elif profile == "m12":
                self.time_label.font_size = 64
                self.date_label.font_size = 26
                self.alarm_info_label.font_size = 22
                self.info_label.font_size = 22
                self.time_label.size_hint = (1, 0.34)
                self.date_label.size_hint = (1, 0.13)
                self.alarm_info_label.size_hint = (1, 0.07)

            else:
                self.time_label.font_size = clock_time_font()
                self.date_label.font_size = clock_date_font()
                self.alarm_info_label.font_size = alarm_info_font()
                self.info_label.font_size = clock_info_font()
                self.time_label.size_hint = (1, 0.34)
                self.date_label.size_hint = (1, 0.13)
                self.alarm_info_label.size_hint = (1, 0.07)

        else:
            if profile == "phone":
                self.time_label.font_size = 104
                self.date_label.font_size = 40
                self.alarm_info_label.font_size = 36
                self.info_label.font_size = 34

            elif profile == "tablet":
                self.time_label.font_size = 84
                self.date_label.font_size = 34
                self.alarm_info_label.font_size = 28
                self.info_label.font_size = 28

            elif profile == "m12":
                self.time_label.font_size = 72
                self.date_label.font_size = 28
                self.alarm_info_label.font_size = 22
                self.info_label.font_size = 22

            else:
                self.time_label.font_size = clock_time_font()
                self.date_label.font_size = clock_date_font()
                self.alarm_info_label.font_size = alarm_info_font()
                self.info_label.font_size = clock_info_font()

            self.time_label.size_hint = (1, 0.34)
            self.date_label.size_hint = (1, 0.13)
            self.alarm_info_label.size_hint = (1, 0.07)

    def update_clock(self, dt):
        now = datetime.now()
        portrait = Window.height > Window.width

        if portrait:
            self.time_label.text = now.strftime("%I:%M\n%p")
            self.date_label.text = now.strftime("%a, %b %d, %Y")
        else:
            self.time_label.text = now.strftime("%I:%M:%S %p")
            self.date_label.text = now.strftime("%A, %B %d, %Y")

    def refresh_alarm_info(self):
        try:
            if not ALARMS_FILE.exists():
                self.alarm_info_label.text = "No Alarm"
                return

            alarms = json.loads(
                ALARMS_FILE.read_text(encoding="utf-8")
            )

            if not alarms:
                self.alarm_info_label.text = "No Alarm"
                return

            alarm = alarms[0]

            if not alarm.get("enabled", False):
                self.alarm_info_label.text = "No Alarm"
                return

            hour = int(alarm.get("hour", 0))
            minute = int(alarm.get("minute", 0))

            self.alarm_info_label.text = f"Alarm {hour:02d}:{minute:02d}"

        except Exception as e:
            log.error(f"Clock: alarm info failed {e}")
            self.alarm_info_label.text = "No Alarm"

    def go_back(self, instance):
        log.info("Clock: Back pressed")
        self.manager.current = "home"

    def open_stopwatch(self, instance):
        log.info("Clock: Stopwatch pressed")
        self.manager.current = "stopwatch"

    def open_timer(self, instance):
        log.info("Clock: Timer pressed")
        self.manager.current = "timer"

    def open_alarm(self, instance):
        log.info("Clock: Alarm pressed")

        if self.manager and self.manager.has_screen("alarm"):
            self.manager.current = "alarm"
        else:
            log.error("Clock: alarm screen missing")
