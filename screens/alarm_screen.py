import json
from datetime import datetime, timedelta
from pathlib import Path

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from utils.logger import log


BASE_DIR = Path(__file__).resolve().parent.parent
ALARMS_FILE = BASE_DIR / "data" / "alarms" / "alarms.json"

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class AlarmScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.alarm_hour = 7
        self.alarm_minute = 30
        self.enabled = False
        self.repeat_mode = "once"
        self.days = []
        self.until_date = ""

        root = BoxLayout(orientation="vertical", spacing=6, padding=10)

        top = BoxLayout(size_hint=(1, 0.08), spacing=8)

        back_btn = Button(
            text="< Back",
            font_size=20,
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        back_btn.bind(on_press=self.go_back)
        top.add_widget(back_btn)
        root.add_widget(top)

        self.current_time = Label(
            text="00:00:00",
            font_size=30,
            bold=True,
            size_hint=(1, 0.10)
        )
        root.add_widget(self.current_time)

        self.alarm_label = Label(
            text="07:30",
            font_size=42,
            bold=True,
            size_hint=(1, 0.11)
        )
        root.add_widget(self.alarm_label)

        row1 = BoxLayout(size_hint=(1, 0.08), spacing=6)
        row1.add_widget(self.make_button("- Hour", lambda x: self.change_hour(-1)))
        row1.add_widget(self.make_button("+ Hour", lambda x: self.change_hour(1)))
        root.add_widget(row1)

        row2 = BoxLayout(size_hint=(1, 0.08), spacing=6)
        row2.add_widget(self.make_button("- Min", lambda x: self.change_minute(-1)))
        row2.add_widget(self.make_button("+ Min", lambda x: self.change_minute(1)))
        root.add_widget(row2)

        self.enable_btn = Button(
            text="Alarm OFF",
            size_hint=(1, 0.08),
            background_normal="",
            background_color=(0.45, 0.15, 0.15, 1)
        )
        self.enable_btn.bind(on_press=self.toggle_alarm)
        root.add_widget(self.enable_btn)

        repeat_row = BoxLayout(size_hint=(1, 0.08), spacing=6)

        self.once_btn = self.make_button("Once", self.set_once)
        self.every_btn = self.make_button("Every Day", self.set_every_day)
        self.days_btn = self.make_button("Days", self.set_days_mode)

        repeat_row.add_widget(self.once_btn)
        repeat_row.add_widget(self.every_btn)
        repeat_row.add_widget(self.days_btn)
        root.add_widget(repeat_row)

        days_row = BoxLayout(size_hint=(1, 0.08), spacing=3)
        self.day_buttons = {}

        for day in DAY_NAMES:
            btn = Button(
                text=day,
                font_size=16,
                background_normal="",
                background_color=(0.10, 0.15, 0.25, 1)
            )
            btn.bind(on_press=lambda instance, d=day: self.toggle_day(d))
            self.day_buttons[day] = btn
            days_row.add_widget(btn)

        root.add_widget(days_row)

        root.add_widget(Label(
            text="Repeat Until   None = Forever",
            font_size=16,
            size_hint=(1, 0.05)
        ))

        month_row = BoxLayout(size_hint=(1, 0.07), spacing=6)
        month_row.add_widget(self.make_button("- Month", lambda x: self.change_until_month(-1)))
        self.until_month_label = Label(text="None", font_size=18)
        month_row.add_widget(self.until_month_label)
        month_row.add_widget(self.make_button("+ Month", lambda x: self.change_until_month(1)))
        root.add_widget(month_row)

        day_row = BoxLayout(size_hint=(1, 0.07), spacing=6)
        day_row.add_widget(self.make_button("- Day", lambda x: self.change_until_day(-1)))
        self.until_day_label = Label(text="--", font_size=18)
        day_row.add_widget(self.until_day_label)
        day_row.add_widget(self.make_button("+ Day", lambda x: self.change_until_day(1)))
        root.add_widget(day_row)

        year_row = BoxLayout(size_hint=(1, 0.07), spacing=6)
        year_row.add_widget(self.make_button("- Year", lambda x: self.change_until_year(-1)))
        self.until_year_label = Label(text="----", font_size=18)
        year_row.add_widget(self.until_year_label)
        year_row.add_widget(self.make_button("+ Year", lambda x: self.change_until_year(1)))
        root.add_widget(year_row)

        clear_until_btn = Button(
            text="Clear Until",
            font_size=18,
            size_hint=(1, 0.07),
            background_normal="",
            background_color=(0.35, 0.15, 0.15, 1)
        )
        clear_until_btn.bind(on_press=self.clear_until)
        root.add_widget(clear_until_btn)

        action_row = BoxLayout(size_hint=(1, 0.08), spacing=6)

        save_btn = Button(
            text="Save",
            background_normal="",
            background_color=(0.10, 0.45, 0.20, 1)
        )
        save_btn.bind(on_press=self.save_alarm)

        delete_btn = Button(
            text="Delete",
            background_normal="",
            background_color=(0.50, 0.15, 0.15, 1)
        )
        delete_btn.bind(on_press=self.delete_alarm)

        action_row.add_widget(save_btn)
        action_row.add_widget(delete_btn)
        root.add_widget(action_row)

        self.status_label = Label(text="", font_size=16, size_hint=(1, 0.07))
        root.add_widget(self.status_label)

        self.add_widget(root)

    def make_button(self, text, callback):
        btn = Button(
            text=text,
            font_size=16,
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        btn.bind(on_press=callback)
        return btn

    def on_enter(self):
        self.load_alarm()
        Clock.unschedule(self.update_clock)
        Clock.schedule_interval(self.update_clock, 1)
        self.update_clock(0)

    def on_leave(self):
        Clock.unschedule(self.update_clock)

    def update_clock(self, dt):
        self.current_time.text = datetime.now().strftime("%I:%M:%S %p")

    def update_alarm_label(self):
        self.alarm_label.text = f"{self.alarm_hour:02d}:{self.alarm_minute:02d}"

    def change_hour(self, delta):
        self.alarm_hour = (self.alarm_hour + delta) % 24
        self.update_alarm_label()

    def change_minute(self, delta):
        self.alarm_minute = (self.alarm_minute + delta) % 60
        self.update_alarm_label()

    def toggle_alarm(self, instance):
        self.enabled = not self.enabled
        self.update_enable_button()

    def update_enable_button(self):
        if self.enabled:
            self.enable_btn.text = "Alarm ON"
            self.enable_btn.background_color = (0.10, 0.45, 0.20, 1)
        else:
            self.enable_btn.text = "Alarm OFF"
            self.enable_btn.background_color = (0.45, 0.15, 0.15, 1)

    def set_once(self, instance):
        self.repeat_mode = "once"
        self.update_repeat_buttons()

    def set_every_day(self, instance):
        self.repeat_mode = "every_day"
        self.days = []
        self.update_repeat_buttons()

    def set_days_mode(self, instance):
        self.repeat_mode = "days"
        self.update_repeat_buttons()

    def toggle_day(self, day):
        self.repeat_mode = "days"

        if day in self.days:
            self.days.remove(day)
        else:
            self.days.append(day)

        self.update_repeat_buttons()

    def update_repeat_buttons(self):
        off = (0.12, 0.20, 0.35, 1)
        on = (0.10, 0.45, 0.20, 1)

        self.once_btn.background_color = on if self.repeat_mode == "once" else off
        self.every_btn.background_color = on if self.repeat_mode == "every_day" else off
        self.days_btn.background_color = on if self.repeat_mode == "days" else off

        for day, btn in self.day_buttons.items():
            btn.background_color = on if day in self.days else (0.10, 0.15, 0.25, 1)

    def ensure_until_date(self):
        if not self.until_date:
            self.until_date = datetime.now().strftime("%Y-%m-%d")

    def get_until_dt(self):
        self.ensure_until_date()
        return datetime.strptime(self.until_date, "%Y-%m-%d")

    def set_until_dt(self, dt):
        self.until_date = dt.strftime("%Y-%m-%d")
        self.update_until_label()

    def days_in_month(self, year, month):
        if month == 12:
            next_month = datetime(year + 1, 1, 1)
        else:
            next_month = datetime(year, month + 1, 1)

        this_month = datetime(year, month, 1)
        return (next_month - this_month).days

    def change_until_month(self, delta):
        try:
            dt = self.get_until_dt()

            month = dt.month + delta
            year = dt.year

            if month < 1:
                month = 12
                year -= 1

            if month > 12:
                month = 1
                year += 1

            day = min(dt.day, self.days_in_month(year, month))
            self.set_until_dt(dt.replace(year=year, month=month, day=day))

        except Exception as e:
            self.status_label.text = str(e)

    def change_until_day(self, delta):
        try:
            dt = self.get_until_dt()
            self.set_until_dt(dt + timedelta(days=delta))
        except Exception as e:
            self.status_label.text = str(e)

    def change_until_year(self, delta):
        try:
            dt = self.get_until_dt()
            year = dt.year + delta
            day = min(dt.day, self.days_in_month(year, dt.month))
            self.set_until_dt(dt.replace(year=year, day=day))
        except Exception as e:
            self.status_label.text = str(e)

    def clear_until(self, instance):
        self.until_date = ""
        self.update_until_label()

    def update_until_label(self):
        if not self.until_date:
            self.until_month_label.text = "None"
            self.until_day_label.text = "--"
            self.until_year_label.text = "----"
            return

        try:
            dt = datetime.strptime(self.until_date, "%Y-%m-%d")
            self.until_month_label.text = dt.strftime("%b")
            self.until_day_label.text = dt.strftime("%d")
            self.until_year_label.text = dt.strftime("%Y")
        except Exception:
            self.until_month_label.text = "Err"
            self.until_day_label.text = "--"
            self.until_year_label.text = "----"

    def save_alarm(self, instance):
        try:
            ALARMS_FILE.parent.mkdir(parents=True, exist_ok=True)

            if self.repeat_mode == "days" and not self.days:
                self.status_label.text = "Select days or choose Once"
                return

            data = [
                {
                    "hour": self.alarm_hour,
                    "minute": self.alarm_minute,
                    "enabled": self.enabled,
                    "repeat_mode": self.repeat_mode,
                    "days": self.days,
                    "until_date": self.until_date,
                    "last_fired_date": "",
                    "last_fired_time": ""
                }
            ]

            ALARMS_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self.status_label.text = "Alarm saved"
            log.info("Alarm saved")

        except Exception as e:
            self.status_label.text = str(e)

    def load_alarm(self):
        try:
            if not ALARMS_FILE.exists():
                self.update_alarm_label()
                self.update_enable_button()
                self.update_repeat_buttons()
                self.update_until_label()
                return

            data = json.loads(ALARMS_FILE.read_text(encoding="utf-8"))

            if not data:
                return

            alarm = data[0]

            self.alarm_hour = int(alarm.get("hour", 7))
            self.alarm_minute = int(alarm.get("minute", 30))
            self.enabled = bool(alarm.get("enabled", False))
            self.repeat_mode = alarm.get("repeat_mode", "once")
            self.days = alarm.get("days", [])
            self.until_date = alarm.get("until_date", "")

            self.update_alarm_label()
            self.update_enable_button()
            self.update_repeat_buttons()
            self.update_until_label()

        except Exception as e:
            log.error(f"Alarm load failed {e}")

    def delete_alarm(self, instance):
        try:
            if ALARMS_FILE.exists():
                ALARMS_FILE.unlink()

            self.enabled = False
            self.repeat_mode = "once"
            self.days = []
            self.until_date = ""

            self.update_enable_button()
            self.update_repeat_buttons()
            self.update_until_label()

            self.status_label.text = "Alarm deleted"

        except Exception as e:
            self.status_label.text = str(e)

    def go_back(self, instance):
        self.manager.current = "clock"
