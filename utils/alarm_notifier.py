import json
import subprocess
from datetime import datetime
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from utils.logger import log
from utils.ui_scale import font, height


BASE_DIR = Path(__file__).resolve().parent.parent
ALARMS_FILE = BASE_DIR / "data" / "alarms" / "alarms.json"
SOUND_FILE = BASE_DIR / "data" / "sounds" / "reminder.wav"

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class AlarmNotifier:
    def __init__(self, interval_seconds=30):
        self.interval_seconds = interval_seconds
        self.running = False
        self.popup_open = False

    def start(self):
        if self.running:
            return

        self.running = True

        Clock.unschedule(self.check)
        Clock.schedule_interval(self.check, self.interval_seconds)
        Clock.schedule_once(lambda dt: self.check(0), 2)

        log.info("AlarmNotifier: started")

    def stop(self):
        Clock.unschedule(self.check)
        self.running = False
        log.info("AlarmNotifier: stopped")

    def load_alarms(self):
        if not ALARMS_FILE.exists():
            return []

        try:
            data = json.loads(ALARMS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception as e:
            log.error(f"AlarmNotifier: load failed {e}")
            return []

    def save_alarms(self, alarms):
        try:
            ALARMS_FILE.parent.mkdir(parents=True, exist_ok=True)
            ALARMS_FILE.write_text(json.dumps(alarms, indent=4), encoding="utf-8")
        except Exception as e:
            log.error(f"AlarmNotifier: save failed {e}")

    def should_ring_today(self, alarm, now):
        if not alarm.get("enabled", False):
            return False

        until_date = str(alarm.get("until_date", "")).strip()

        if until_date:
            try:
                until = datetime.strptime(until_date, "%Y-%m-%d").date()
                if now.date() > until:
                    return False
            except Exception:
                pass

        repeat_mode = alarm.get("repeat_mode", "once")
        today_name = DAY_NAMES[now.weekday()]

        if repeat_mode == "every_day":
            return True

        if repeat_mode == "days":
            days = alarm.get("days", [])
            return today_name in days

        return True

    def check(self, dt):
        alarms = self.load_alarms()

        if not alarms:
            return

        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        now_hm = now.strftime("%H:%M")
        changed = False

        for alarm in alarms:
            if not self.should_ring_today(alarm, now):
                continue

            alarm_hm = f"{int(alarm.get('hour', 0)):02d}:{int(alarm.get('minute', 0)):02d}"

            if alarm_hm != now_hm:
                continue

            if alarm.get("last_fired_date") == today and alarm.get("last_fired_time") == alarm_hm:
                continue

            alarm["last_fired_date"] = today
            alarm["last_fired_time"] = alarm_hm
            changed = True

            if alarm.get("repeat_mode", "once") == "once":
                alarm["enabled"] = False

            self.show_popup(alarm)

        if changed:
            self.save_alarms(alarms)

    def play_sound(self):
        try:
            if not SOUND_FILE.exists():
                log.warning(f"AlarmNotifier: sound missing {SOUND_FILE}")
                print("\a", end="", flush=True)
                return

            if platform == "macosx":
                subprocess.Popen(
                    ["afplay", str(SOUND_FILE)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                log.info(f"AlarmNotifier: sound played {SOUND_FILE}")
                return

            print("\a", end="", flush=True)
            log.info("AlarmNotifier: fallback bell used")

        except Exception as e:
            log.error(f"AlarmNotifier: sound failed {e}")

    def show_popup(self, alarm):
        if self.popup_open:
            return

        app = App.get_running_app()

        if not app:
            return

        self.popup_open = True
        self.play_sound()

        hour = int(alarm.get("hour", 0))
        minute = int(alarm.get("minute", 0))

        message = f"ALARM\n\n{hour:02d}:{minute:02d}"

        box = BoxLayout(
            orientation="vertical",
            padding=height(10),
            spacing=height(8)
        )

        label = Label(
            text=message,
            font_size=font(34),
            bold=True,
            halign="center",
            valign="middle"
        )
        label.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - height(20), val[1])))

        box.add_widget(label)

        popup = Popup(
            title="Alarm Clock",
            content=box,
            size_hint=(0.90, 0.70),
            auto_dismiss=False
        )

        dismiss_btn = Button(
            text="Dismiss",
            font_size=font(28),
            size_hint=(1, 0.22),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )

        def close_popup(instance):
            self.popup_open = False
            popup.dismiss()

        dismiss_btn.bind(on_press=close_popup)
        box.add_widget(dismiss_btn)

        popup.open()
        log.info(f"AlarmNotifier: popup shown {hour:02d}:{minute:02d}")