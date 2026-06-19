# M12 OS Alarm Screen - multiple alarms version
import json
from datetime import datetime, timedelta
from pathlib import Path

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout

from utils.logger import log
from utils.ui_scale import (
    device_profile,
    title_font,
    button_font,
    text_font,
    status_font,
    clock_time_font,
    clock_date_font,
    button_height,
    row_height,
    padding_size,
    spacing_size,
)


BASE_DIR = Path(__file__).resolve().parent.parent
ALARMS_FILE = BASE_DIR / "data" / "alarms" / "alarms.json"

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def day_button_font():
    profile = device_profile()

    if profile == "phone":
        return 34
    if profile == "tablet":
        return 28
    if profile == "m12":
        return 22

    return status_font()


def alarm_small_label_font():
    profile = device_profile()

    if profile == "phone":
        return 40
    if profile == "tablet":
        return 30
    if profile == "m12":
        return 24

    return text_font()


def alarm_current_time_font():
    profile = device_profile()

    if profile == "desktop":
        return status_font()

    return clock_date_font()


def alarm_big_time_font():
    profile = device_profile()

    if profile == "desktop":
        return title_font()

    return clock_time_font()


def alarm_button_height():
    profile = device_profile()

    if profile == "phone":
        return int(button_height() * 0.78)
    if profile == "tablet":
        return int(button_height() * 0.72)
    if profile == "m12":
        return int(button_height() * 0.68)

    return int(button_height() * 0.62)


def alarm_main_button_height():
    profile = device_profile()

    if profile == "phone":
        return int(button_height() * 0.88)
    if profile == "tablet":
        return int(button_height() * 0.82)
    if profile == "m12":
        return int(button_height() * 0.78)

    return int(button_height() * 0.72)


def alarm_list_row_height():
    profile = device_profile()

    if profile == "phone":
        return int(row_height() * 0.56)
    if profile == "tablet":
        return int(row_height() * 0.52)
    if profile == "m12":
        return int(row_height() * 0.50)

    return int(row_height() * 0.50)


def alarm_current_time_hint():
    profile = device_profile()

    if profile == "phone":
        return 0.065
    if profile == "tablet":
        return 0.055
    if profile == "m12":
        return 0.050

    return 0.040


def alarm_big_time_hint():
    profile = device_profile()

    if profile == "phone":
        return 0.080
    if profile == "tablet":
        return 0.070
    if profile == "m12":
        return 0.065

    return 0.055


def alarm_list_hint():
    profile = device_profile()

    if profile == "phone":
        return 0.34
    if profile == "tablet":
        return 0.36
    if profile == "m12":
        return 0.37

    return 0.40


def alarm_label_hint():
    profile = device_profile()

    if profile == "phone":
        return 0.035
    if profile == "tablet":
        return 0.032
    if profile == "m12":
        return 0.030

    return 0.028


def alarm_status_hint():
    profile = device_profile()

    if profile == "phone":
        return 0.045
    if profile == "tablet":
        return 0.040
    if profile == "m12":
        return 0.038

    return 0.035


def alarm_current_display_font():
    profile = device_profile()

    if profile == "phone":
        return int(clock_date_font() * 0.80)
    if profile == "tablet":
        return int(clock_date_font() * 0.82)
    if profile == "m12":
        return int(clock_date_font() * 0.85)

    return status_font()


def alarm_time_display_font():
    profile = device_profile()

    if profile == "phone":
        return int(clock_time_font() * 0.78)
    if profile == "tablet":
        return int(clock_time_font() * 0.78)
    if profile == "m12":
        return int(clock_time_font() * 0.78)

    return int(title_font() * 0.82)


def alarm_control_font():
    profile = device_profile()

    if profile == "phone":
        return int(button_font() * 0.72)
    if profile == "tablet":
        return int(button_font() * 0.74)
    if profile == "m12":
        return int(button_font() * 0.76)

    return int(button_font() * 0.78)


def alarm_list_font():
    profile = device_profile()

    if profile == "phone":
        return int(text_font() * 0.80)
    if profile == "tablet":
        return int(text_font() * 0.82)
    if profile == "m12":
        return int(text_font() * 0.86)

    return int(text_font() * 0.90)



class AlarmScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.alarms = []
        self.selected_index = None

        self.alarm_hour = 7
        self.alarm_minute = 30
        self.enabled = True
        self.repeat_mode = "once"
        self.days = []
        self.until_date = ""

        root = BoxLayout(
            orientation="vertical",
            spacing=spacing_size(),
            padding=padding_size()
        )

        top = BoxLayout(
            size_hint=(1, None),
            height=alarm_main_button_height(),
            spacing=spacing_size()
        )

        back_btn = Button(
            text="< Back",
            font_size=alarm_control_font(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        back_btn.bind(on_press=self.go_back)
        top.add_widget(back_btn)

        new_btn = Button(
            text="New",
            font_size=alarm_control_font(),
            background_normal="",
            background_color=(0.10, 0.45, 0.20, 1)
        )
        new_btn.bind(on_press=self.new_alarm)
        top.add_widget(new_btn)

        root.add_widget(top)

        self.current_time = Label(
            text="00:00:00",
            font_size=alarm_current_display_font(),
            bold=True,
            size_hint=(1, alarm_current_time_hint())
        )
        root.add_widget(self.current_time)

        self.alarm_label = Label(
            text="07:30",
            font_size=alarm_time_display_font(),
            bold=True,
            size_hint=(1, alarm_big_time_hint())
        )
        root.add_widget(self.alarm_label)

        scroll = ScrollView(
            size_hint=(1, alarm_list_hint()),
            do_scroll_x=False,
            do_scroll_y=True
        )

        self.alarm_list = GridLayout(
            cols=1,
            spacing=spacing_size(),
            size_hint_y=None
        )
        self.alarm_list.bind(minimum_height=self.alarm_list.setter("height"))

        scroll.add_widget(self.alarm_list)
        root.add_widget(scroll)

        row1 = BoxLayout(
            size_hint=(1, None),
            height=alarm_button_height(),
            spacing=spacing_size()
        )
        row1.add_widget(self.make_button("- Hour", lambda x: self.change_hour(-1)))
        row1.add_widget(self.make_button("+ Hour", lambda x: self.change_hour(1)))
        root.add_widget(row1)

        row2 = BoxLayout(
            size_hint=(1, None),
            height=alarm_button_height(),
            spacing=spacing_size()
        )
        row2.add_widget(self.make_button("- Min", lambda x: self.change_minute(-1)))
        row2.add_widget(self.make_button("+ Min", lambda x: self.change_minute(1)))
        root.add_widget(row2)

        self.enable_btn = Button(
            text="Alarm ON",
            font_size=alarm_control_font(),
            size_hint=(1, None),
            height=alarm_main_button_height(),
            background_normal="",
            background_color=(0.10, 0.45, 0.20, 1)
        )
        self.enable_btn.bind(on_press=self.toggle_alarm)
        root.add_widget(self.enable_btn)

        repeat_row = BoxLayout(
            size_hint=(1, None),
            height=alarm_button_height(),
            spacing=spacing_size()
        )

        self.once_btn = self.make_button("Once", self.set_once)
        self.every_btn = self.make_button("Every Day", self.set_every_day)
        self.days_btn = self.make_button("Days", self.set_days_mode)

        repeat_row.add_widget(self.once_btn)
        repeat_row.add_widget(self.every_btn)
        repeat_row.add_widget(self.days_btn)
        root.add_widget(repeat_row)

        days_row = BoxLayout(
            size_hint=(1, None),
            height=alarm_button_height(),
            spacing=spacing_size()
        )
        self.day_buttons = {}

        for day in DAY_NAMES:
            btn = Button(
                text=day,
                font_size=max(12, int(day_button_font() * 0.82)),
                background_normal="",
                background_color=(0.10, 0.15, 0.25, 1)
            )
            btn.bind(on_press=lambda instance, d=day: self.toggle_day(d))
            self.day_buttons[day] = btn
            days_row.add_widget(btn)

        root.add_widget(days_row)

        root.add_widget(Label(
            text="Repeat Until   None = Forever",
            font_size=status_font(),
            size_hint=(1, alarm_label_hint())
        ))

        month_row = BoxLayout(
            size_hint=(1, None),
            height=alarm_button_height(),
            spacing=spacing_size()
        )
        month_row.add_widget(self.make_button("- Month", lambda x: self.change_until_month(-1)))
        self.until_month_label = Label(text="None", font_size=max(12, int(alarm_small_label_font() * 0.78)))
        month_row.add_widget(self.until_month_label)
        month_row.add_widget(self.make_button("+ Month", lambda x: self.change_until_month(1)))
        root.add_widget(month_row)

        day_row = BoxLayout(
            size_hint=(1, None),
            height=alarm_button_height(),
            spacing=spacing_size()
        )
        day_row.add_widget(self.make_button("- Day", lambda x: self.change_until_day(-1)))
        self.until_day_label = Label(text="--", font_size=max(12, int(alarm_small_label_font() * 0.78)))
        day_row.add_widget(self.until_day_label)
        day_row.add_widget(self.make_button("+ Day", lambda x: self.change_until_day(1)))
        root.add_widget(day_row)

        year_row = BoxLayout(
            size_hint=(1, None),
            height=alarm_button_height(),
            spacing=spacing_size()
        )
        year_row.add_widget(self.make_button("- Year", lambda x: self.change_until_year(-1)))
        self.until_year_label = Label(text="----", font_size=max(12, int(alarm_small_label_font() * 0.78)))
        year_row.add_widget(self.until_year_label)
        year_row.add_widget(self.make_button("+ Year", lambda x: self.change_until_year(1)))
        root.add_widget(year_row)

        action_row = BoxLayout(
            size_hint=(1, None),
            height=alarm_main_button_height(),
            spacing=spacing_size()
        )

        clear_until_btn = Button(
            text="Clear Until",
            font_size=alarm_control_font(),
            background_normal="",
            background_color=(0.35, 0.15, 0.15, 1)
        )
        clear_until_btn.bind(on_press=self.clear_until)
        action_row.add_widget(clear_until_btn)

        save_btn = Button(
            text="Save",
            font_size=alarm_control_font(),
            background_normal="",
            background_color=(0.10, 0.45, 0.20, 1)
        )
        save_btn.bind(on_press=self.save_alarm)
        action_row.add_widget(save_btn)

        delete_btn = Button(
            text="Delete",
            font_size=alarm_control_font(),
            background_normal="",
            background_color=(0.50, 0.15, 0.15, 1)
        )
        delete_btn.bind(on_press=self.delete_alarm)
        action_row.add_widget(delete_btn)

        root.add_widget(action_row)

        self.status_label = Label(
            text="",
            font_size=status_font(),
            size_hint=(1, alarm_status_hint())
        )
        root.add_widget(self.status_label)

        self.add_widget(root)

    def make_button(self, text, callback):
        btn = Button(
            text=text,
            font_size=alarm_control_font(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        btn.bind(on_press=callback)
        return btn

    def on_enter(self):
        self.load_alarms()

        if self.alarms and self.selected_index is None:
            self.select_alarm(0)
        elif not self.alarms:
            self.new_alarm(None)

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

    def alarm_to_state(self, alarm):
        self.alarm_hour = int(alarm.get("hour", 7))
        self.alarm_minute = int(alarm.get("minute", 30))
        self.enabled = bool(alarm.get("enabled", True))
        self.repeat_mode = alarm.get("repeat_mode", "once")
        self.days = list(alarm.get("days", []))
        self.until_date = alarm.get("until_date", "")

        self.update_alarm_label()
        self.update_enable_button()
        self.update_repeat_buttons()
        self.update_until_label()

    def state_to_alarm(self):
        return {
            "hour": self.alarm_hour,
            "minute": self.alarm_minute,
            "enabled": self.enabled,
            "repeat_mode": self.repeat_mode,
            "days": list(self.days),
            "until_date": self.until_date,
            "last_fired_date": "",
            "last_fired_time": ""
        }

    def alarm_summary(self, alarm):
        hour = int(alarm.get("hour", 0))
        minute = int(alarm.get("minute", 0))
        enabled = bool(alarm.get("enabled", False))
        repeat_mode = alarm.get("repeat_mode", "once")
        days = alarm.get("days", [])
        until_date = alarm.get("until_date", "")

        if repeat_mode == "every_day":
            repeat_text = "Every Day"
        elif repeat_mode == "days":
            repeat_text = " ".join(days) if days else "Days"
        else:
            repeat_text = "Once"

        if until_date:
            repeat_text += f" Until {until_date}"

        prefix = "ON" if enabled else "OFF"
        return f"{prefix}  {hour:02d}:{minute:02d}  {repeat_text}"

    def rebuild_alarm_list(self):
        self.alarm_list.clear_widgets()

        if not self.alarms:
            self.alarm_list.add_widget(Label(
                text="No alarms. Press New.",
                font_size=alarm_list_font(),
                size_hint_y=None,
                height=alarm_list_row_height()
            ))
            return

        for index, alarm in enumerate(self.alarms):
            btn = Button(
                text=self.alarm_summary(alarm),
                font_size=alarm_list_font(),
                size_hint_y=None,
                height=alarm_list_row_height(),
                background_normal="",
                background_color=(0.25, 0.45, 0.75, 1)
                if index == self.selected_index
                else (0.10, 0.15, 0.25, 1),
                halign="left",
                valign="middle"
            )
            btn.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - spacing_size(), val[1])))
            btn.bind(on_press=lambda instance, i=index: self.select_alarm(i))
            self.alarm_list.add_widget(btn)

    def select_alarm(self, index):
        if index < 0 or index >= len(self.alarms):
            return

        self.selected_index = index
        self.alarm_to_state(self.alarms[index])
        self.status_label.text = f"Selected alarm {index + 1}"
        self.rebuild_alarm_list()

    def new_alarm(self, instance):
        self.selected_index = None
        self.alarm_hour = 7
        self.alarm_minute = 30
        self.enabled = True
        self.repeat_mode = "once"
        self.days = []
        self.until_date = ""

        self.update_alarm_label()
        self.update_enable_button()
        self.update_repeat_buttons()
        self.update_until_label()
        self.rebuild_alarm_list()

        self.status_label.text = "New alarm. Set time and Save."

    def load_alarms(self):
        try:
            if not ALARMS_FILE.exists():
                self.alarms = []
                self.rebuild_alarm_list()
                return

            data = json.loads(ALARMS_FILE.read_text(encoding="utf-8"))

            if isinstance(data, list):
                self.alarms = data
            else:
                self.alarms = []

            if self.selected_index is not None and self.selected_index >= len(self.alarms):
                self.selected_index = None

            self.rebuild_alarm_list()

        except Exception as e:
            log.error(f"Alarm load failed {e}")
            self.alarms = []
            self.rebuild_alarm_list()

    def save_alarms_file(self):
        ALARMS_FILE.parent.mkdir(parents=True, exist_ok=True)
        ALARMS_FILE.write_text(json.dumps(self.alarms, indent=4), encoding="utf-8")

    def save_alarm(self, instance):
        try:
            if self.repeat_mode == "days" and not self.days:
                self.status_label.text = "Select days or choose Once"
                return

            alarm = self.state_to_alarm()

            if self.selected_index is None:
                self.alarms.append(alarm)
                self.selected_index = len(self.alarms) - 1
                message = "Alarm Added"
            else:
                self.alarms[self.selected_index] = alarm
                message = "Alarm Updated"

            self.save_alarms_file()
            self.rebuild_alarm_list()

            self.status_label.text = message
            log.info(message)

            if self.manager and self.manager.has_screen("home"):
                home = self.manager.get_screen("home")
                if hasattr(home, "refresh_clock_button"):
                    home.refresh_clock_button()

        except Exception as e:
            self.status_label.text = str(e)

    def delete_alarm(self, instance):
        try:
            if self.selected_index is None:
                self.status_label.text = "Select alarm first."
                return

            if 0 <= self.selected_index < len(self.alarms):
                del self.alarms[self.selected_index]

            if self.alarms:
                self.selected_index = min(self.selected_index, len(self.alarms) - 1)
                self.alarm_to_state(self.alarms[self.selected_index])
            else:
                self.selected_index = None
                self.new_alarm(None)

            self.save_alarms_file()
            self.rebuild_alarm_list()

            self.status_label.text = "Alarm Deleted"

            if self.manager and self.manager.has_screen("home"):
                home = self.manager.get_screen("home")
                if hasattr(home, "refresh_clock_button"):
                    home.refresh_clock_button()

        except Exception as e:
            self.status_label.text = str(e)

    def go_back(self, instance):
        self.manager.current = "clock"
