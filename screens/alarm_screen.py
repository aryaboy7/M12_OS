# M12 OS Alarm Screen - multiple alarms version
import json
from datetime import datetime, timedelta
from pathlib import Path

from kivy.utils import platform

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup

from utils.logger import log
from utils.text_editor_popup import open_text_editor
from services.android_clock_alarm_scheduler import (
    sync_android_clock_alarms,
)
from utils.system_header import create_system_header
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
from utils.data_paths import ALARMS_FILE

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



def stop_native_clock_alarm():
    """
    Stop the native Android Clock alarm ringtone, if it is currently ringing.
    Safe no-op on desktop/Linux/macOS.
    """
    if platform != "android":
        return

    try:
        from jnius import autoclass

        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )
        Intent = autoclass(
            "android.content.Intent"
        )
        ClockAlarmReceiver = autoclass(
            "com.m12os.m12os.ClockAlarmReceiver"
        )

        activity = PythonActivity.mActivity

        intent = Intent(
            activity,
            ClockAlarmReceiver,
        )
        intent.setAction(
            "com.m12os.CLOCK_ALARM_STOP"
        )

        activity.sendBroadcast(intent)

        log.info(
            "Native Clock alarm STOP broadcast sent."
        )

    except Exception as error:
        log.error(
            "Native Clock alarm stop failed: "
            f"{type(error).__name__}: {error}"
        )


class AlarmScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.alarms = []
        self.selected_index = None

        self.alarm_name = ""
        self.alarm_hour = 7
        self.alarm_minute = 30
        self.enabled = True
        self.repeat_mode = "once"
        self.days = []
        now = datetime.now()
        self.once_date = now.strftime("%Y-%m-%d")
        self.yearly_month = now.month
        self.yearly_day = now.day
        self.until_date = ""

        root = BoxLayout(
            orientation="vertical",
            spacing=spacing_size(),
            padding=padding_size()
        )

        self.system_header = create_system_header(
            title="Alarm",
            back_callback=self.go_back,
            status_provider=self.get_system_status_text,
            ai_active=False,
        )
        root.add_widget(self.system_header)

        top = BoxLayout(
            size_hint=(1, None),
            height=alarm_main_button_height(),
            spacing=spacing_size(),
        )

        new_btn = Button(
            text="New",
            font_size=alarm_control_font(),
            background_normal="",
            background_color=(0.10, 0.45, 0.20, 1),
        )
        new_btn.bind(on_press=self.new_alarm)
        top.add_widget(new_btn)

        self.name_input = TextInput(
            text="",
            hint_text="Alarm Name",
            font_size=alarm_control_font(),
            multiline=False,
            size_hint=(2.2, 1),
            use_bubble=False,
            use_handles=False,
            readonly=(device_profile() == "m12"),
        )

        if device_profile() == "m12":
            self.name_input.bind(
                on_touch_down=self.name_touched
            )

        top.add_widget(self.name_input)

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
        self.yearly_btn = self.make_button("Yearly", self.set_yearly_mode)

        repeat_row.add_widget(self.once_btn)
        repeat_row.add_widget(self.every_btn)
        repeat_row.add_widget(self.days_btn)
        repeat_row.add_widget(self.yearly_btn)
        root.add_widget(repeat_row)

        # Only the controls needed by the selected repeat mode are shown.
        self.repeat_options_box = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=0,
            spacing=spacing_size(),
        )
        root.add_widget(self.repeat_options_box)

        action_row = BoxLayout(
            size_hint=(1, None),
            height=alarm_main_button_height(),
            spacing=spacing_size()
        )

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
        def wrapped_callback(instance):
            stop_native_clock_alarm()
            return callback(instance)

        btn.bind(on_press=wrapped_callback)
        return btn

    def name_touched(self, instance, touch):
        if instance.collide_point(*touch.pos):
            self.open_name_editor()
            return True

        return False

    def open_name_editor(self):
        def save_text(value):
            self.name_input.text = str(value).strip()

        open_text_editor(
            title="Alarm Name",
            text=self.name_input.text,
            on_save=save_text,
            multiline=False,
        )

    def get_system_status_text(self):
        if (
            self.manager
            and self.manager.has_screen("home")
        ):
            home = self.manager.get_screen("home")
            provider = getattr(
                home,
                "get_system_status_text",
                None,
            )

            if callable(provider):
                return provider()

        return "WiFi"

    def on_enter(self):
        # Opening the Alarm screen should silence any native Clock alarm
        # that is currently ringing.
        stop_native_clock_alarm()

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
        if not self.once_date:
            self.once_date = datetime.now().strftime("%Y-%m-%d")
        self.update_repeat_buttons()

    def set_every_day(self, instance):
        self.repeat_mode = "every_day"
        self.days = []
        self.update_repeat_buttons()

    def set_days_mode(self, instance):
        self.repeat_mode = "days"
        self.update_repeat_buttons()

    def set_yearly_mode(self, instance):
        self.repeat_mode = "yearly"
        self.days = []
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
        self.yearly_btn.background_color = on if self.repeat_mode == "yearly" else off

        self.rebuild_repeat_options()

    def rebuild_repeat_options(self):
        if not hasattr(self, "repeat_options_box"):
            return

        self.repeat_options_box.clear_widgets()
        row_height_value = alarm_button_height()

        if self.repeat_mode == "days":
            days_row = BoxLayout(
                size_hint=(1, None),
                height=row_height_value,
                spacing=spacing_size(),
            )
            self.day_buttons = {}

            off = (0.10, 0.15, 0.25, 1)
            on = (0.10, 0.45, 0.20, 1)

            for day in DAY_NAMES:
                btn = Button(
                    text=day,
                    font_size=max(12, int(day_button_font() * 0.82)),
                    background_normal="",
                    background_color=on if day in self.days else off,
                )
                btn.bind(
                    on_press=lambda instance, d=day: self.toggle_day(d)
                )
                self.day_buttons[day] = btn
                days_row.add_widget(btn)

            self.repeat_options_box.add_widget(days_row)
            self.repeat_options_box.height = row_height_value
            return

        if self.repeat_mode in ("once", "yearly"):
            date_row = BoxLayout(
                size_hint=(1, None),
                height=row_height_value,
                spacing=spacing_size(),
            )

            label_text = "Date" if self.repeat_mode == "once" else "Yearly Date"
            date_row.add_widget(
                Label(
                    text=label_text,
                    font_size=alarm_small_label_font(),
                    size_hint_x=0.32,
                )
            )

            date_btn = Button(
                text=self.selected_date_display(),
                font_size=alarm_control_font(),
                background_normal="",
                background_color=(0.12, 0.20, 0.35, 1),
                size_hint_x=0.68,
            )
            date_btn.bind(on_press=self.open_alarm_date_picker)
            date_row.add_widget(date_btn)

            self.repeat_options_box.add_widget(date_row)
            self.repeat_options_box.height = row_height_value
            return

        # Every Day needs no additional controls.
        self.repeat_options_box.height = 0

    def selected_date_display(self):
        if self.repeat_mode == "yearly":
            try:
                return datetime(
                    2024,
                    int(self.yearly_month),
                    int(self.yearly_day),
                ).strftime("%B %d")
            except Exception:
                return "Select Date"

        try:
            return datetime.strptime(
                self.once_date,
                "%Y-%m-%d",
            ).strftime("%b %d, %Y")
        except Exception:
            return "Select Date"

    def open_alarm_date_picker(self, instance=None):
        if self.repeat_mode == "yearly":
            # Use a leap year internally so February 29 can be selected.
            current = datetime(
                2024,
                int(self.yearly_month),
                int(self.yearly_day),
            )
            yearly = True
        else:
            try:
                current = datetime.strptime(
                    self.once_date,
                    "%Y-%m-%d",
                )
            except Exception:
                current = datetime.now()
            yearly = False

        values = {
            "year": current.year,
            "month": current.month,
            "day": current.day,
        }

        box = BoxLayout(
            orientation="vertical",
            spacing=spacing_size(),
            padding=padding_size(),
        )

        display = Label(
            text=self.format_picker_date(values, yearly),
            font_size=alarm_big_time_font(),
            bold=True,
            size_hint=(1, 0.18),
        )
        box.add_widget(display)

        def refresh():
            self.clamp_picker_day(values, yearly)
            display.text = self.format_picker_date(values, yearly)

        def add_row(label, key):
            row = BoxLayout(
                orientation="horizontal",
                spacing=spacing_size(),
                size_hint=(1, 0.20),
            )

            minus = self.make_button("-", lambda inst: None)
            middle = Label(
                text=label,
                font_size=alarm_control_font(),
                bold=True,
            )
            plus = self.make_button("+", lambda inst: None)

            def dec(_instance):
                values[key] -= 1

                if key == "month" and values[key] < 1:
                    values[key] = 12
                    if not yearly:
                        values["year"] -= 1

                if key == "day" and values[key] < 1:
                    values[key] = self.days_in_month(
                        2024 if yearly else values["year"],
                        values["month"],
                    )

                refresh()

            def inc(_instance):
                values[key] += 1

                if key == "month" and values[key] > 12:
                    values[key] = 1
                    if not yearly:
                        values["year"] += 1

                max_day = self.days_in_month(
                    2024 if yearly else values["year"],
                    values["month"],
                )
                if key == "day" and values[key] > max_day:
                    values[key] = 1

                refresh()

            minus.bind(on_press=dec)
            plus.bind(on_press=inc)

            row.add_widget(minus)
            row.add_widget(middle)
            row.add_widget(plus)
            box.add_widget(row)

        if not yearly:
            add_row("Year", "year")

        add_row("Month", "month")
        add_row("Day", "day")

        pop = Popup(
            title="Pick Yearly Date" if yearly else "Pick Alarm Date",
            content=box,
            size_hint=(0.90, 0.78 if not yearly else 0.68),
        )

        buttons = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, 0.18),
        )

        def today(_instance):
            now = datetime.now()
            values["year"] = 2024 if yearly else now.year
            values["month"] = now.month
            values["day"] = now.day
            refresh()

        def ok(_instance):
            self.clamp_picker_day(values, yearly)

            if yearly:
                self.yearly_month = values["month"]
                self.yearly_day = values["day"]
            else:
                self.once_date = (
                    f"{values['year']:04}-"
                    f"{values['month']:02}-"
                    f"{values['day']:02}"
                )

            pop.dismiss()
            self.rebuild_repeat_options()

        buttons.add_widget(self.make_button("Today", today))
        buttons.add_widget(self.make_button("OK", ok))
        buttons.add_widget(
            self.make_button(
                "Cancel",
                lambda inst: pop.dismiss(),
            )
        )
        box.add_widget(buttons)
        pop.open()

    def days_in_month(self, year, month):
        if month == 12:
            next_month = datetime(year + 1, 1, 1)
        else:
            next_month = datetime(year, month + 1, 1)

        return (next_month - datetime(year, month, 1)).days

    def clamp_picker_day(self, values, yearly=False):
        year = 2024 if yearly else values["year"]
        max_day = self.days_in_month(year, values["month"])
        values["day"] = max(1, min(values["day"], max_day))

    def format_picker_date(self, values, yearly=False):
        year = 2024 if yearly else values["year"]

        try:
            dt = datetime(
                year,
                values["month"],
                values["day"],
            )
            if yearly:
                return dt.strftime("%A\n%B %d")
            return dt.strftime("%A\n%B %d, %Y")
        except Exception:
            if yearly:
                return (
                    f"{values['month']:02}-"
                    f"{values['day']:02}"
                )
            return (
                f"{values['year']:04}-"
                f"{values['month']:02}-"
                f"{values['day']:02}"
            )

    def alarm_to_state(self, alarm):
        self.alarm_name = str(
            alarm.get("name", "")
        ).strip()
        self.name_input.text = self.alarm_name

        self.alarm_hour = int(alarm.get("hour", 7))
        self.alarm_minute = int(alarm.get("minute", 30))
        self.enabled = bool(alarm.get("enabled", True))
        self.repeat_mode = alarm.get("repeat_mode", "once")
        self.days = list(alarm.get("days", []))
        now = datetime.now()
        self.once_date = str(alarm.get("date", "")).strip() or now.strftime("%Y-%m-%d")
        self.yearly_month = int(alarm.get("yearly_month", now.month))
        self.yearly_day = int(alarm.get("yearly_day", now.day))
        self.until_date = alarm.get("until_date", "")

        self.yearly_month = max(1, min(self.yearly_month, 12))
        max_day = self.days_in_month(2024, self.yearly_month)
        self.yearly_day = max(1, min(self.yearly_day, max_day))

        self.update_alarm_label()
        self.update_enable_button()
        self.update_repeat_buttons()

    def state_to_alarm(self):
        self.alarm_name = self.name_input.text.strip()

        return {
            "name": self.alarm_name,
            "hour": self.alarm_hour,
            "minute": self.alarm_minute,
            "enabled": self.enabled,
            "repeat_mode": self.repeat_mode,
            "days": list(self.days),
            "date": self.once_date if self.repeat_mode == "once" else "",
            "yearly_month": int(self.yearly_month),
            "yearly_day": int(self.yearly_day),
            "until_date": "",
            "last_fired_date": "",
            "last_fired_time": ""
        }

    def alarm_summary(self, alarm):
        name = str(
            alarm.get("name", "")
        ).strip()
        hour = int(alarm.get("hour", 0))
        minute = int(alarm.get("minute", 0))
        enabled = bool(alarm.get("enabled", False))
        repeat_mode = alarm.get("repeat_mode", "once")
        days = alarm.get("days", [])
        yearly_month = int(alarm.get("yearly_month", 1))
        yearly_day = int(alarm.get("yearly_day", 1))
        once_date = str(alarm.get("date", "")).strip()

        if repeat_mode == "every_day":
            repeat_text = "Every Day"
        elif repeat_mode == "days":
            repeat_text = " ".join(days) if days else "Days"
        elif repeat_mode == "yearly":
            try:
                yearly_date = datetime(
                    2024,
                    yearly_month,
                    yearly_day,
                )
                repeat_text = (
                    "Yearly "
                    + yearly_date.strftime("%b %d")
                )
            except ValueError:
                repeat_text = "Yearly"
        else:
            if once_date:
                try:
                    repeat_text = "Once " + datetime.strptime(
                        once_date,
                        "%Y-%m-%d",
                    ).strftime("%b %d, %Y")
                except ValueError:
                    repeat_text = "Once"
            else:
                repeat_text = "Once"


        prefix = "ON" if enabled else "OFF"
        display_name = name or "Alarm"

        return (
            f"{prefix}  {hour:02d}:{minute:02d}  "
            f"{display_name}  {repeat_text}"
        )

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
        self.alarm_name = ""
        self.name_input.text = ""
        self.alarm_hour = 7
        self.alarm_minute = 30
        self.enabled = True
        self.repeat_mode = "once"
        self.days = []
        now = datetime.now()
        self.once_date = now.strftime("%Y-%m-%d")
        self.yearly_month = now.month
        self.yearly_day = now.day
        self.until_date = ""

        self.update_alarm_label()
        self.update_enable_button()
        self.update_repeat_buttons()
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
        ALARMS_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        ALARMS_FILE.write_text(
            json.dumps(
                self.alarms,
                indent=4,
            ),
            encoding="utf-8",
        )

        # On Android, mirror the saved Clock alarms into AlarmManager.
        # This lets them fire while Kivy/Python is suspended and the
        # device screen is locked.
        try:
            sync_android_clock_alarms(
                self.alarms
            )
        except Exception as error:
            log.error(
                "Clock native alarm sync failed: "
                f"{type(error).__name__}: {error}"
            )

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

    def go_back(self, instance=None):
        self.manager.current = "clock"