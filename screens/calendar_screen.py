import json
from datetime import datetime, timedelta
from pathlib import Path

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner

from utils.ui_scale import (
    device_profile,
    font,
    height,
    title_font,
    button_font,
    list_font,
    text_font,
    input_font,
    status_font,
    small_font,
    padding_size,
    spacing_size,
)
from utils.logger import log
from utils.text_editor_popup import open_text_editor


Window.softinput_mode = "resize"

BASE_DIR = Path(__file__).resolve().parent.parent
EVENTS_DIR = BASE_DIR / "data" / "events"
EVENTS_FILE = EVENTS_DIR / "events.json"
EVENTS_DIR.mkdir(parents=True, exist_ok=True)

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

REMINDER_OPTIONS = [
    "None",
    "Event Time",
    "5m",
    "15m",
    "30m",
    "1h",
    "1 day",
]

REMINDER_MINUTES = {
    "None": None,
    "Event Time": 0,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "1 day": 1440,
}

OLD_REMINDER_MAP = {
    "At event time": "Event Time",
    "At time": "Event Time",
    "5 minutes before": "5m",
    "15 minutes before": "15m",
    "30 minutes before": "30m",
    "1 hour before": "1h",
    "1 day before": "1 day",
}


def calendar_filter_font():
    profile = device_profile()

    if profile == "phone":
        return 40
    if profile == "tablet":
        return 30
    if profile == "m12":
        return 24

    return font(13)


def compact_button_font():
    profile = device_profile()

    if profile == "phone":
        return 36
    if profile == "tablet":
        return 28
    if profile == "m12":
        return 22

    return font(12)


def cal_font(base):
    """
    Compatibility helper for older Calendar code.
    New Calendar UI follows shared M12 OS sizes from ui_scale.py.
    """
    if base <= 13:
        return compact_button_font()
    if base <= 16:
        return list_font()
    if base <= 18:
        return input_font()
    if base <= 22:
        return button_font()
    if base <= 30:
        return title_font()

    return font(base)


def event_row_height():
    profile = device_profile()

    if profile == "phone":
        return height(220)
    if profile == "tablet":
        return height(185)
    if profile == "m12":
        return height(160)

    return height(130)


class CalendarScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.events = []
        self.selected_index = None
        self.mode = "list"
        self.active_filter = "upcoming"

        self.repeat_mode = "once"
        self.days = []
        self.until_date = ""

        self.root_box = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size()
        )
        self.add_widget(self.root_box)
        self.build_list_view()

    def load_events(self):
        if not EVENTS_FILE.exists():
            return []
        try:
            data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception as e:
            log.error(f"Calendar: load failed {e}")
        return []

    def save_events(self):
        try:
            EVENTS_FILE.write_text(json.dumps(self.events, indent=4), encoding="utf-8")
            log.info("Calendar: events saved")
        except Exception as e:
            log.error(f"Calendar: save failed {e}")

    def normalize_event(self, event):
        reminder = str(event.get("reminder", "None")).strip() or "None"
        reminder = OLD_REMINDER_MAP.get(reminder, reminder)
        if reminder not in REMINDER_OPTIONS:
            reminder = "None"

        repeat_mode = event.get("repeat_mode", "once")
        if repeat_mode not in ("once", "every_day", "days"):
            repeat_mode = "once"

        days = event.get("days", [])
        if not isinstance(days, list):
            days = []

        return {
            "title": str(event.get("title", "")).strip() or "Untitled Event",
            "date": str(event.get("date", "")).strip(),
            "time": str(event.get("time", "")).strip(),
            "notes": str(event.get("notes", "")).strip(),
            "reminder": reminder,
            "repeat_mode": repeat_mode,
            "days": days,
            "until_date": str(event.get("until_date", "")).strip(),
            "last_reminder_date": str(event.get("last_reminder_date", "")).strip(),
            "last_event_date": str(event.get("last_event_date", "")).strip(),
            "reminder_notified": bool(event.get("reminder_notified", event.get("notified", False))),
            "event_notified": bool(event.get("event_notified", False))
        }

    def parse_event_datetime(self, event):
        try:
            date_text = event.get("date", "").strip()
            time_text = event.get("time", "").strip() or "00:00"
            return datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")
        except Exception:
            return None

    def get_today_occurrence(self, event, now=None):
        if now is None:
            now = datetime.now()

        base_dt = self.parse_event_datetime(event)
        if not base_dt:
            return None

        repeat_mode = event.get("repeat_mode", "once")
        today = now.date()

        if repeat_mode == "once":
            return base_dt

        if today < base_dt.date():
            return None

        until_date = str(event.get("until_date", "")).strip()
        if until_date:
            try:
                until = datetime.strptime(until_date, "%Y-%m-%d").date()
                if today > until:
                    return None
            except Exception:
                pass

        if repeat_mode == "every_day":
            return datetime.combine(today, base_dt.time())

        if repeat_mode == "days":
            today_name = DAY_NAMES[now.weekday()]
            days = event.get("days", [])
            if today_name not in days:
                return None
            return datetime.combine(today, base_dt.time())

        return base_dt

    def next_occurrence(self, event):
        now = datetime.now()
        base_dt = self.parse_event_datetime(event)

        if not base_dt:
            return None

        repeat_mode = event.get("repeat_mode", "once")

        if repeat_mode == "once":
            return base_dt

        today = now.date()
        until_date = str(event.get("until_date", "")).strip()
        until = None

        if until_date:
            try:
                until = datetime.strptime(until_date, "%Y-%m-%d").date()
            except Exception:
                until = None

        for offset in range(0, 370):
            day = today + timedelta(days=offset)

            if day < base_dt.date():
                continue

            if until and day > until:
                return None

            if repeat_mode == "every_day":
                candidate = datetime.combine(day, base_dt.time())
            elif repeat_mode == "days":
                day_name = DAY_NAMES[day.weekday()]
                if day_name not in event.get("days", []):
                    continue
                candidate = datetime.combine(day, base_dt.time())
            else:
                return base_dt

            if candidate >= now:
                return candidate

        return None

    def sort_events(self):
        self.events = sorted(
            self.events,
            key=lambda e: self.next_occurrence(e) or self.parse_event_datetime(e) or datetime.max
        )

    def countdown_text(self, event):
        dt = self.next_occurrence(event)

        if not dt:
            return "No upcoming occurrence"

        diff = dt - datetime.now()
        if diff.total_seconds() < 0:
            return "Past event"

        days = diff.days
        seconds = diff.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60

        if days > 0:
            return f"In {days}d {hours}h {minutes}m"
        if hours > 0:
            return f"In {hours}h {minutes}m"
        return f"In {minutes}m"

    def reminder_datetime(self, event):
        reminder = event.get("reminder", "None")
        minutes = REMINDER_MINUTES.get(reminder)

        if minutes is None:
            return None

        event_dt = self.next_occurrence(event)
        if not event_dt:
            return None

        return event_dt - timedelta(minutes=minutes)

    def reminder_display_text(self, event):
        reminder = event.get("reminder", "None")

        if reminder == "None":
            return "Notification: None"

        if reminder == "Event Time":
            return "Notification: Event Time"

        remind_at = self.reminder_datetime(event)

        if not remind_at:
            return f"Notification: {reminder}"

        return f"Notification: {reminder} before  Notify: {remind_at.strftime('%m/%d %I:%M %p')}"

    def repeat_display_text(self, event):
        mode = event.get("repeat_mode", "once")

        if mode == "every_day":
            text = "Repeat: Every Day"
        elif mode == "days":
            days = event.get("days", [])
            text = "Repeat: " + (", ".join(days) if days else "Days")
        else:
            text = "Repeat: Once"

        until = str(event.get("until_date", "")).strip()
        if until:
            try:
                dt = datetime.strptime(until, "%Y-%m-%d")
                text += f" until {dt.strftime('%b %d, %Y')}"
            except Exception:
                text += f" until {until}"

        return text

    def event_display_text(self, event):
        title = event.get("title", "Untitled Event")
        dt = self.next_occurrence(event) or self.parse_event_datetime(event)
        when = dt.strftime("%Y-%m-%d %H:%M") if dt else f"{event.get('date', '')} {event.get('time', '')}"
        reminder_line = self.reminder_display_text(event)
        repeat_line = self.repeat_display_text(event)

        return f"{title}\n{when}\nCountdown: {self.countdown_text(event)}\n{reminder_line}\n{repeat_line}"

    def event_color(self, event, selected=False):
        if selected:
            return (0.25, 0.45, 0.75, 1)

        dt = self.next_occurrence(event) or self.parse_event_datetime(event)
        if not dt:
            return (0.10, 0.15, 0.25, 1)

        seconds = (dt - datetime.now()).total_seconds()
        if seconds < 0:
            return (0.28, 0.28, 0.28, 1)
        if seconds <= 3600:
            return (0.55, 0.12, 0.12, 1)
        if seconds <= 86400:
            return (0.55, 0.45, 0.10, 1)
        return (0.12, 0.20, 0.35, 1)

    def filtered_events_with_indexes(self):
        now = datetime.now()
        today = now.date()
        result = []

        for index, event in enumerate(self.events):
            dt = self.next_occurrence(event)

            if not dt:
                dt = self.parse_event_datetime(event)

            if not dt:
                continue

            if self.active_filter == "upcoming":
                if dt >= now:
                    result.append((index, event))

            elif self.active_filter == "today":
                occurrence = self.get_today_occurrence(event, now)

                if occurrence and occurrence.date() == today and occurrence >= now:
                    result.append((index, event))

            elif self.active_filter == "tomorrow":
                if dt >= now and (dt.date() - today).days == 1:
                    result.append((index, event))

            elif self.active_filter == "week":
                days = (dt.date() - today).days
                if dt >= now and 0 <= days <= 7:
                    result.append((index, event))

            elif self.active_filter == "past":
                base_dt = self.parse_event_datetime(event)
                if base_dt and base_dt < now and event.get("repeat_mode", "once") == "once":
                    result.append((index, event))

            elif self.active_filter == "all":
                result.append((index, event))

        return result

    def on_enter(self):
        self.events = [self.normalize_event(e) for e in self.load_events()]
        self.sort_events()
        self.build_list_view()
        Clock.unschedule(self.refresh_countdowns)
        Clock.schedule_interval(self.refresh_countdowns, 60)

    def on_leave(self):
        Clock.unschedule(self.refresh_countdowns)

    def refresh_countdowns(self, dt):
        if self.mode == "list":
            self.build_list_view()

    def clear(self):
        self.root_box.clear_widgets()

    def make_btn(self, text, callback, color=(0.10, 0.15, 0.25, 1), fs=18):
        if fs <= 13:
            use_font = compact_button_font()
        elif fs <= 16:
            use_font = calendar_filter_font()
        else:
            use_font = button_font()

        btn = Button(
            text=text,
            font_size=use_font,
            background_normal="",
            background_color=color
        )
        btn.bind(on_press=callback)
        return btn

    def set_filter(self, name):
        self.active_filter = name
        self.selected_index = None
        self.build_list_view()

    def build_list_view(self, *args):
        self.mode = "list"
        self.clear()

        self.root_box.add_widget(Label(
            text="Calendar Events",
            font_size=title_font(),
            bold=True,
            size_hint=(1, 0.08)
        ))

        filters = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.08))
        for label, key in [
            ("Upcoming", "upcoming"),
            ("Today", "today"),
            ("Tomorrow", "tomorrow"),
            ("Week", "week"),
            ("Past", "past"),
        ]:
            color = (0.25, 0.45, 0.75, 1) if self.active_filter == key else (0.10, 0.15, 0.25, 1)
            filters.add_widget(self.make_btn(label, lambda inst, k=key: self.set_filter(k), color, fs=13))
        self.root_box.add_widget(filters)

        scroll = ScrollView(size_hint=(1, 0.57), do_scroll_x=False, do_scroll_y=True)

        self.list_box = GridLayout(cols=1, spacing=spacing_size(), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))

        visible_events = self.filtered_events_with_indexes()

        if not self.events:
            self.list_box.add_widget(Label(
                text="No events yet.\nPress Add Event.",
                font_size=button_font(),
                size_hint_y=None,
                height=event_row_height() * 2
            ))
        elif not visible_events:
            self.list_box.add_widget(Label(
                text="No events for this filter.",
                font_size=button_font(),
                size_hint_y=None,
                height=event_row_height()
            ))
        else:
            for index, event in visible_events:
                btn = Button(
                    text=self.event_display_text(event),
                    font_size=list_font(),
                    size_hint_y=None,
                    height=event_row_height(),
                    halign="left",
                    valign="middle",
                    background_normal="",
                    background_color=self.event_color(event, index == self.selected_index)
                )
                btn.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - spacing_size(), val[1])))
                btn.bind(on_press=lambda inst, i=index: self.select_event(i))
                self.list_box.add_widget(btn)

        scroll.add_widget(self.list_box)
        self.root_box.add_widget(scroll)

        buttons1 = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.10))
        buttons1.add_widget(self.make_btn("Add", self.add_event_view, (0.12, 0.20, 0.35, 1)))
        buttons1.add_widget(self.make_btn("Edit", self.edit_selected_event))
        buttons1.add_widget(self.make_btn("Delete", self.delete_selected_event, (0.35, 0.12, 0.12, 1)))
        self.root_box.add_widget(buttons1)

        buttons2 = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.10))
        buttons2.add_widget(self.make_btn("Refresh", self.build_list_view))
        buttons2.add_widget(self.make_btn("< Back", self.go_back))
        self.root_box.add_widget(buttons2)

    def select_event(self, index):
        self.selected_index = index
        log.info(f"Calendar: selected event {index}")
        self.build_list_view()

    def add_event_view(self, *args):
        self.build_edit_view(None)

    def edit_selected_event(self, *args):
        if self.selected_index is None:
            return
        if self.selected_index < 0 or self.selected_index >= len(self.events):
            return
        self.build_edit_view(self.selected_index)

    def delete_selected_event(self, *args):
        if self.selected_index is None:
            return
        if self.selected_index < 0 or self.selected_index >= len(self.events):
            return

        deleted = self.events.pop(self.selected_index)
        self.selected_index = None
        self.save_events()
        log.info(f"Calendar: deleted {deleted.get('title')}")
        self.build_list_view()

    def build_edit_view(self, index):
        self.mode = "edit"
        self.clear()

        is_new = index is None
        now = datetime.now()
        default_hour = min(now.hour + 1, 23)

        event = {
            "title": "",
            "date": now.strftime("%Y-%m-%d"),
            "time": f"{default_hour:02}:00",
            "notes": "",
            "reminder": "None",
            "repeat_mode": "once",
            "days": [],
            "until_date": "",
            "last_reminder_date": "",
            "last_event_date": "",
            "reminder_notified": False,
            "event_notified": False
        }

        if not is_new:
            event = dict(self.events[index])

        self.root_box.add_widget(Label(
            text="Add Event" if is_new else "Edit Event",
            font_size=title_font(),
            bold=True,
            size_hint=(1, 0.07)
        ))

        self.title_input = TextInput(
            text=event.get("title", ""),
            hint_text="Event title",
            font_size=input_font(),
            multiline=False,
            size_hint=(1, 0.075),
            use_bubble=False,
            use_handles=False,
            readonly=(device_profile() == "m12")
        )

        if device_profile() == "m12":
            self.title_input.bind(on_touch_down=self.title_touched)

        self.root_box.add_widget(self.title_input)

        date_time_row = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.075))

        self.date_input = TextInput(
            text=event.get("date", ""),
            hint_text="Tap date",
            font_size=input_font(),
            multiline=False,
            readonly=True,
            use_bubble=False,
            use_handles=False
        )
        self.date_input.bind(on_touch_down=self.date_field_touched)

        self.time_input = TextInput(
            text=event.get("time", ""),
            hint_text="Tap time",
            font_size=input_font(),
            multiline=False,
            readonly=True,
            use_bubble=False,
            use_handles=False
        )
        self.time_input.bind(on_touch_down=self.time_field_touched)

        date_time_row.add_widget(self.date_input)
        date_time_row.add_widget(self.time_input)
        self.root_box.add_widget(date_time_row)

        self.notes_input = TextInput(
            text=event.get("notes", ""),
            hint_text="Notes",
            font_size=list_font(),
            multiline=True,
            size_hint=(1, 0.14),
            use_bubble=False,
            use_handles=False,
            readonly=(device_profile() == "m12")
        )

        if device_profile() == "m12":
            self.notes_input.bind(on_touch_down=self.notes_touched)

        self.root_box.add_widget(self.notes_input)

        reminder_text = event.get("reminder", "None")
        if reminder_text not in REMINDER_OPTIONS:
            reminder_text = "None"

        self.reminder_spinner = Spinner(
            text=reminder_text,
            values=REMINDER_OPTIONS,
            font_size=input_font(),
            size_hint=(1, 0.075),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        self.root_box.add_widget(self.reminder_spinner)

        self.repeat_mode = event.get("repeat_mode", "once")
        self.days = list(event.get("days", []))
        self.until_date = event.get("until_date", "")

        repeat_row = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.07))

        self.once_btn = self.make_btn("Once", self.set_once, fs=12)
        self.every_btn = self.make_btn("Every Day", self.set_every_day, fs=12)
        self.days_btn = self.make_btn("Days", self.set_days_mode, fs=12)

        repeat_row.add_widget(self.once_btn)
        repeat_row.add_widget(self.every_btn)
        repeat_row.add_widget(self.days_btn)
        self.root_box.add_widget(repeat_row)

        days_row = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.07))
        self.day_buttons = {}

        for day in DAY_NAMES:
            btn = self.make_btn(day, lambda inst, d=day: self.toggle_day(d), fs=11)
            self.day_buttons[day] = btn
            days_row.add_widget(btn)

        self.root_box.add_widget(days_row)

        until_label = Label(
            text="Repeat Until   None = Forever",
            font_size=compact_button_font(),
            size_hint=(1, 0.04)
        )
        self.root_box.add_widget(until_label)

        until_row = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.065))

        until_row.add_widget(self.make_btn("-M", lambda x: self.change_until_month(-1), fs=11))
        self.until_month_label = Label(text="None", font_size=compact_button_font())
        until_row.add_widget(self.until_month_label)

        until_row.add_widget(self.make_btn("-D", lambda x: self.change_until_day(-1), fs=11))
        self.until_day_label = Label(text="--", font_size=compact_button_font())
        until_row.add_widget(self.until_day_label)

        until_row.add_widget(self.make_btn("-Y", lambda x: self.change_until_year(-1), fs=11))
        self.until_year_label = Label(text="----", font_size=compact_button_font())
        until_row.add_widget(self.until_year_label)

        self.root_box.add_widget(until_row)

        until_row2 = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.065))

        until_row2.add_widget(self.make_btn("+M", lambda x: self.change_until_month(1), fs=11))
        until_row2.add_widget(self.make_btn("+D", lambda x: self.change_until_day(1), fs=11))
        until_row2.add_widget(self.make_btn("+Y", lambda x: self.change_until_year(1), fs=11))
        until_row2.add_widget(self.make_btn("Clear Until", self.clear_until, (0.35, 0.12, 0.12, 1), fs=11))

        self.root_box.add_widget(until_row2)

        self.update_repeat_buttons()
        self.update_until_label()

        self.status_label = Label(
            text="",
            font_size=status_font(),
            size_hint=(1, 0.035),
            halign="center",
            valign="middle"
        )
        self.status_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.root_box.add_widget(self.status_label)

        buttons = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.09))
        buttons.add_widget(self.make_btn("Save", lambda inst: self.save_event(index), (0.12, 0.20, 0.35, 1)))
        buttons.add_widget(self.make_btn("Cancel", self.build_list_view))
        self.root_box.add_widget(buttons)

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
        off = (0.10, 0.15, 0.25, 1)
        on = (0.10, 0.45, 0.20, 1)

        self.once_btn.background_color = on if self.repeat_mode == "once" else off
        self.every_btn.background_color = on if self.repeat_mode == "every_day" else off
        self.days_btn.background_color = on if self.repeat_mode == "days" else off

        for day, btn in self.day_buttons.items():
            btn.background_color = on if day in self.days else off

    def ensure_until_date(self):
        if not self.until_date:
            self.until_date = datetime.now().strftime("%Y-%m-%d")

    def get_until_dt(self):
        self.ensure_until_date()
        return datetime.strptime(self.until_date, "%Y-%m-%d")

    def set_until_dt(self, dt):
        self.until_date = dt.strftime("%Y-%m-%d")
        self.update_until_label()

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

    def title_touched(self, instance, touch):
        if instance.collide_point(*touch.pos):
            self.open_title_editor()
            return True
        return False

    def notes_touched(self, instance, touch):
        if instance.collide_point(*touch.pos):
            self.open_notes_editor()
            return True
        return False

    def open_title_editor(self):
        def save_text(value):
            self.title_input.text = value

        open_text_editor(
            title="Event Title",
            text=self.title_input.text,
            on_save=save_text,
            multiline=False
        )

    def open_notes_editor(self):
        def save_text(value):
            self.notes_input.text = value

        open_text_editor(
            title="Event Notes",
            text=self.notes_input.text,
            on_save=save_text,
            multiline=True
        )

    def hide_keyboard(self, *args):
        for name in ("title_input", "notes_input", "date_input", "time_input"):
            try:
                getattr(self, name).focus = False
            except Exception:
                pass

        try:
            Window.release_all_keyboards()
        except Exception:
            pass

    def date_field_touched(self, instance, touch):
        if instance.collide_point(*touch.pos):
            self.hide_keyboard()
            self.open_date_picker()
            return True
        return False

    def time_field_touched(self, instance, touch):
        if instance.collide_point(*touch.pos):
            self.hide_keyboard()
            self.open_time_picker()
            return True
        return False

    def open_date_picker(self):
        try:
            current = datetime.strptime(self.date_input.text.strip(), "%Y-%m-%d")
        except Exception:
            current = datetime.now()

        values = {"year": current.year, "month": current.month, "day": current.day}

        box = BoxLayout(orientation="vertical", spacing=spacing_size(), padding=padding_size())
        display = Label(text=self.format_picker_date(values), font_size=cal_font(26), bold=True, size_hint=(1, 0.18))
        box.add_widget(display)

        def refresh():
            self.clamp_day(values)
            display.text = self.format_picker_date(values)

        def add_row(label, key):
            row = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.18))
            minus = self.make_btn("-", lambda inst: None, (0.35, 0.12, 0.12, 1), fs=28)
            mid = Label(text=label, font_size=button_font(), bold=True)
            plus = self.make_btn("+", lambda inst: None, (0.12, 0.20, 0.35, 1), fs=28)

            def dec(instance):
                values[key] -= 1
                if key == "month" and values[key] < 1:
                    values[key] = 12
                    values["year"] -= 1
                if key == "day" and values[key] < 1:
                    values[key] = self.days_in_month(values["year"], values["month"])
                refresh()

            def inc(instance):
                values[key] += 1
                if key == "month" and values[key] > 12:
                    values[key] = 1
                    values["year"] += 1
                if key == "day" and values[key] > self.days_in_month(values["year"], values["month"]):
                    values[key] = 1
                refresh()

            minus.bind(on_press=dec)
            plus.bind(on_press=inc)
            row.add_widget(minus)
            row.add_widget(mid)
            row.add_widget(plus)
            box.add_widget(row)

        add_row("Year", "year")
        add_row("Month", "month")
        add_row("Day", "day")

        pop = Popup(title="Pick Date", content=box, size_hint=(0.90, 0.80))

        buttons = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.16))

        def today(instance):
            n = datetime.now()
            values["year"], values["month"], values["day"] = n.year, n.month, n.day
            refresh()

        def ok(instance):
            self.clamp_day(values)
            self.date_input.text = f"{values['year']:04}-{values['month']:02}-{values['day']:02}"
            pop.dismiss()

        buttons.add_widget(self.make_btn("Today", today, fs=20))
        buttons.add_widget(self.make_btn("OK", ok, (0.12, 0.20, 0.35, 1), fs=20))
        buttons.add_widget(self.make_btn("Cancel", lambda inst: pop.dismiss(), fs=20))
        box.add_widget(buttons)
        pop.open()

    def open_time_picker(self):
        try:
            current = datetime.strptime(self.time_input.text.strip(), "%H:%M")
            values = {"hour": current.hour, "minute": current.minute}
        except Exception:
            n = datetime.now()
            values = {"hour": n.hour, "minute": (n.minute // 5) * 5}

        box = BoxLayout(orientation="vertical", spacing=spacing_size(), padding=padding_size())
        display = Label(text=self.format_picker_time(values), font_size=cal_font(34), bold=True, size_hint=(1, 0.24))
        box.add_widget(display)

        def refresh():
            display.text = self.format_picker_time(values)

        def add_row(label, key, step, max_value):
            row = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.22))
            minus = self.make_btn("-", lambda inst: None, (0.35, 0.12, 0.12, 1), fs=30)
            mid = Label(text=label, font_size=cal_font(24), bold=True)
            plus = self.make_btn("+", lambda inst: None, (0.12, 0.20, 0.35, 1), fs=30)

            def dec(instance):
                values[key] -= step
                if values[key] < 0:
                    values[key] = max_value
                refresh()

            def inc(instance):
                values[key] += step
                if values[key] > max_value:
                    values[key] = 0
                refresh()

            minus.bind(on_press=dec)
            plus.bind(on_press=inc)
            row.add_widget(minus)
            row.add_widget(mid)
            row.add_widget(plus)
            box.add_widget(row)

        add_row("Hour", "hour", 1, 23)
        add_row("Minute", "minute", 5, 55)

        pop = Popup(title="Pick Time", content=box, size_hint=(0.90, 0.72))
        buttons = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.16))

        def now_btn(instance):
            n = datetime.now()
            values["hour"] = n.hour
            values["minute"] = (n.minute // 5) * 5
            refresh()

        def ok(instance):
            self.time_input.text = f"{values['hour']:02}:{values['minute']:02}"
            pop.dismiss()

        buttons.add_widget(self.make_btn("Now", now_btn, fs=20))
        buttons.add_widget(self.make_btn("OK", ok, (0.12, 0.20, 0.35, 1), fs=20))
        buttons.add_widget(self.make_btn("Cancel", lambda inst: pop.dismiss(), fs=20))
        box.add_widget(buttons)
        pop.open()

    def days_in_month(self, year, month):
        if month == 12:
            next_month = datetime(year + 1, 1, 1)
        else:
            next_month = datetime(year, month + 1, 1)
        return (next_month - datetime(year, month, 1)).days

    def clamp_day(self, values):
        max_day = self.days_in_month(values["year"], values["month"])
        values["day"] = max(1, min(values["day"], max_day))

    def format_picker_date(self, values):
        try:
            return datetime(values["year"], values["month"], values["day"]).strftime("%A\n%B %d, %Y")
        except Exception:
            return f"{values['year']:04}-{values['month']:02}-{values['day']:02}"

    def format_picker_time(self, values):
        h = values["hour"]
        m = values["minute"]
        ampm = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12:02}:{m:02} {ampm}\n({h:02}:{m:02})"

    def validate_date_time(self, date_text, time_text):
        try:
            datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")
            return True
        except Exception:
            return False

    def save_event(self, index):
        self.hide_keyboard()

        title = self.title_input.text.strip() or "Untitled Event"
        date_text = self.date_input.text.strip()
        time_text = self.time_input.text.strip() or "00:00"
        notes = self.notes_input.text.strip()
        reminder = self.reminder_spinner.text.strip() if hasattr(self, "reminder_spinner") else "None"

        if reminder not in REMINDER_OPTIONS:
            reminder = "None"

        if self.repeat_mode == "days" and not self.days:
            self.status_label.text = "Select repeat days or choose Once"
            return

        if not date_text:
            self.status_label.text = "Date is required."
            return

        if not self.validate_date_time(date_text, time_text):
            self.status_label.text = "Invalid date/time."
            return

        event = {
            "title": title,
            "date": date_text,
            "time": time_text,
            "notes": notes,
            "reminder": reminder,
            "repeat_mode": self.repeat_mode,
            "days": self.days,
            "until_date": self.until_date,
            "last_reminder_date": "",
            "last_event_date": "",
            "reminder_notified": False,
            "event_notified": False
        }

        if index is None:
            self.events.append(event)
            log.info(f"Calendar: added {title}")
        else:
            self.events[index] = event
            log.info(f"Calendar: edited {title}")

        self.sort_events()
        self.save_events()
        self.selected_index = None
        self.build_list_view()

    def on_touch_down(self, touch):
        try:
            active_inputs = []
            if hasattr(self, "title_input"):
                active_inputs.append(self.title_input)
            if hasattr(self, "notes_input"):
                active_inputs.append(self.notes_input)

            inside_input = any(widget.collide_point(*touch.pos) for widget in active_inputs)

            if not inside_input:
                self.hide_keyboard()
        except Exception:
            pass

        return super().on_touch_down(touch)

    def go_back(self, *args):
        self.manager.current = "home"