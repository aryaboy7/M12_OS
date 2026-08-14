import json
from datetime import datetime, timedelta
from pathlib import Path
import subprocess

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from utils.ui_scale import font, height
from utils.logger import log


BASE_DIR = Path(__file__).resolve().parent.parent
from utils.data_paths import EVENTS_FILE, SOUNDS_DIR
REMINDER_SOUND = SOUNDS_DIR / "reminder.wav"

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

REMINDER_MINUTES = {
    "None": None,
    "Event Time": 0,
    "At time": 0,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "1 day": 1440,

    "At event time": 0,
    "5 minutes before": 5,
    "15 minutes before": 15,
    "30 minutes before": 30,
    "1 hour before": 60,
    "1 day before": 1440,
}


class EventNotifier:
    def __init__(self, interval_seconds=30):
        self.interval_seconds = interval_seconds
        self.running = False
        self.popup_open = False
        self.sound = None

    def start(self):
        if self.running:
            return

        self.running = True

        # Do not preload reminder.wav during application startup.
        # On Linux, SoundLoader.load() can block the Kivy main thread.
        # The sound will be loaded only when a reminder actually fires.
        self.sound = None

        Clock.unschedule(self.check)
        Clock.schedule_interval(self.check, self.interval_seconds)
        Clock.schedule_once(lambda dt: self.check(0), 2)

        log.info("EventNotifier FINAL: started")

    def stop(self):
        Clock.unschedule(self.check)
        self.running = False
        log.info("EventNotifier FINAL: stopped")

    def load_sound(self):
        try:
            if not REMINDER_SOUND.exists():
                self.sound = None
                log.warning(f"EventNotifier FINAL: sound file missing: {REMINDER_SOUND}")
                return

            if platform == "macosx":
                self.sound = None
                log.info(f"EventNotifier FINAL: macOS sound ready for afplay: {REMINDER_SOUND}")
                return

            self.sound = SoundLoader.load(str(REMINDER_SOUND))

            if self.sound:
                log.info(f"EventNotifier FINAL: sound loaded {REMINDER_SOUND}")
            else:
                log.warning(f"EventNotifier FINAL: SoundLoader could not load: {REMINDER_SOUND}")

        except Exception as e:
            self.sound = None
            log.error(f"EventNotifier FINAL: sound load failed {e}")

    def play_sound(self):
        try:
            if not REMINDER_SOUND.exists():
                log.warning(f"EventNotifier FINAL: sound file missing: {REMINDER_SOUND}")
                print("\a", end="", flush=True)
                return

            if platform == "macosx":
                try:
                    subprocess.Popen(
                        ["afplay", str(REMINDER_SOUND)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    log.info(f"EventNotifier FINAL: sound played with afplay {REMINDER_SOUND}")
                    return
                except Exception as e:
                    log.error(f"EventNotifier FINAL: afplay failed {e}")

            if self.sound:
                try:
                    self.sound.stop()
                    self.sound.seek(0)
                except Exception:
                    pass

                self.sound.play()
                log.info("EventNotifier FINAL: sound played with cached SoundLoader")
                return

            sound = SoundLoader.load(str(REMINDER_SOUND))

            if sound:
                self.sound = sound
                sound.play()
                log.info("EventNotifier FINAL: sound loaded late and played")
                return

            print("\a", end="", flush=True)
            log.warning(f"EventNotifier FINAL: SoundLoader could not load {REMINDER_SOUND}")

        except Exception as e:
            log.error(f"EventNotifier FINAL: sound play failed {e}")

    def load_events(self):
        if not EVENTS_FILE.exists():
            return []

        try:
            data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception as e:
            log.error(f"EventNotifier FINAL: load failed {e}")

        return []

    def save_events(self, events):
        try:
            EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            EVENTS_FILE.write_text(json.dumps(events, indent=4), encoding="utf-8")
        except Exception as e:
            log.error(f"EventNotifier FINAL: save failed {e}")

    def normalize_reminder(self, reminder):
        reminder = str(reminder).strip() or "None"

        old_map = {
            "At event time": "Event Time",
            "At time": "Event Time",
            "5 minutes before": "5m",
            "15 minutes before": "15m",
            "30 minutes before": "30m",
            "1 hour before": "1h",
            "1 day before": "1 day",
        }

        return old_map.get(reminder, reminder)

    def parse_event_datetime(self, event):
        try:
            date_text = str(event.get("date", "")).strip()
            time_text = str(event.get("time", "")).strip() or "00:00"
            return datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")
        except Exception:
            return None

    def is_recurring(self, event):
        return event.get("repeat_mode", "once") in ("every_day", "days")

    def get_today_occurrence(self, event, now):
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

    def reminder_datetime_for_occurrence(self, event, occurrence_dt):
        reminder = self.normalize_reminder(event.get("reminder", "None"))
        minutes = REMINDER_MINUTES.get(reminder)

        if minutes is None:
            return None

        return occurrence_dt - timedelta(minutes=minutes)

    def remaining_text(self, occurrence_dt):
        diff = occurrence_dt - datetime.now()

        if diff.total_seconds() <= 0:
            return "Event time is now"

        days = diff.days
        seconds = diff.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60

        if days > 0:
            return f"Starts in {days}d {hours}h {minutes}m"

        if hours > 0:
            return f"Starts in {hours}h {minutes}m"

        return f"Starts in {minutes}m"

    def check(self, dt):
        events = self.load_events()

        if not events:
            return

        now = datetime.now()
        today_key = now.strftime("%Y-%m-%d")
        changed = False

        for event in events:
            reminder = self.normalize_reminder(event.get("reminder", "None"))
            occurrence_dt = self.get_today_occurrence(event, now)

            if not occurrence_dt:
                continue

            recurring = self.is_recurring(event)

            # Reminder popup.
            if reminder != "None":
                remind_at = self.reminder_datetime_for_occurrence(event, occurrence_dt)

                if remind_at and now >= remind_at and now < occurrence_dt:
                    if recurring:
                        if event.get("last_reminder_date", "") != today_key:
                            event["last_reminder_date"] = today_key
                            changed = True
                            self.show_popup(event, occurrence_dt, popup_type="REMINDER")
                    else:
                        if not event.get("reminder_notified", False):
                            event["reminder_notified"] = True
                            changed = True
                            self.show_popup(event, occurrence_dt, popup_type="REMINDER")

            # Event-time popup.
            if now >= occurrence_dt and now <= occurrence_dt + timedelta(minutes=2):
                if recurring:
                    if event.get("last_event_date", "") != today_key:
                        event["last_event_date"] = today_key
                        changed = True
                        self.show_popup(event, occurrence_dt, popup_type="EVENT TIME")
                else:
                    if not event.get("event_notified", False):
                        event["event_notified"] = True
                        changed = True
                        self.show_popup(event, occurrence_dt, popup_type="EVENT TIME")

            elif not recurring and now > occurrence_dt + timedelta(minutes=2):
                if not event.get("event_notified", False):
                    event["event_notified"] = True
                    changed = True

        if changed:
            self.save_events(events)

    def show_popup(self, event, occurrence_dt, popup_type="REMINDER"):
        if self.popup_open:
            return

        app = App.get_running_app()

        if not app:
            return

        self.popup_open = True
        self.play_sound()

        title = event.get("title", "Event")
        notes = event.get("notes", "")
        reminder = self.normalize_reminder(event.get("reminder", "None"))

        repeat_mode = event.get("repeat_mode", "once")
        repeat_text = "Once"

        if repeat_mode == "every_day":
            repeat_text = "Every Day"
        elif repeat_mode == "days":
            repeat_text = "Days: " + ", ".join(event.get("days", []))

        message = (
            f"{popup_type}\n\n"
            f"{title}\n\n"
            f"{occurrence_dt.strftime('%Y-%m-%d %H:%M')}\n"
            f"{self.remaining_text(occurrence_dt)}\n\n"
            f"Reminder: {reminder}\n"
            f"Repeat: {repeat_text}"
        )

        if notes:
            message += f"\n\n{notes}"

        box = BoxLayout(
            orientation="vertical",
            padding=height(10),
            spacing=height(8)
        )

        label = Label(
            text=message,
            font_size=font(22),
            bold=True,
            halign="center",
            valign="middle"
        )
        label.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - height(20), val[1])))

        box.add_widget(label)

        popup = Popup(
            title="Calendar Notification",
            content=box,
            size_hint=(0.90, 0.75),
            auto_dismiss=False
        )

        ok_btn = Button(
            text="OK",
            font_size=font(26),
            size_hint=(1, 0.20),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )

        def close_popup(instance):
            self.popup_open = False
            popup.dismiss()

        ok_btn.bind(on_press=close_popup)
        box.add_widget(ok_btn)

        popup.open()
        log.info(f"EventNotifier FINAL: {popup_type} popup shown for {title}")