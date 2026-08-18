from pathlib import Path
import math
import time

from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.utils import platform
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup

from utils.logger import log
from utils.system_header import create_system_header
from utils.ui_scale import (
    device_profile,
    button_font,
    text_font,
    status_font,
    clock_time_font,
    padding_size,
    spacing_size,
    height,
)


BASE_DIR = Path(__file__).resolve().parent.parent


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
        self._finished_notified = False
        self._finish_sound = None
        self._deadline = None

        root = BoxLayout(
            orientation="vertical",
            spacing=spacing_size(),
            padding=padding_size(),
        )

        self.system_header = create_system_header(
            title="Timer",
            back_callback=self.go_back,
            status_provider=self.get_system_status_text,
            ai_active=False,
        )
        root.add_widget(self.system_header)

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

        self.add_widget(root)

        # IMPORTANT:
        # The timer must keep ticking even when the Timer screen is not open.
        # Schedule it once for the lifetime of this screen object.
        Clock.schedule_interval(self.tick, 1)

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
        log.info("Timer: opened")
        self.update_display()

    def on_leave(self):
        # Do NOT unschedule tick here.
        # AI can start a timer while the user is on another screen.
        pass

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

        self._finished_notified = False
        self.running = True

        # Real deadline: Android may pause Kivy Clock while the display is off,
        # but monotonic time continues to advance.
        self._deadline = time.monotonic() + float(self.remaining)

        # Android owns the wake-up event while the device is asleep.
        self._cancel_android_alarm()
        self._schedule_android_alarm()

        self.status_label.text = "Running"
        log.info(
            f"Timer: started for {int(self.remaining)} seconds"
        )
        self.update_display()

    def stop(self, instance):
        # Save the true remaining time so Resume continues correctly.
        if self.running and self._deadline is not None:
            self.remaining = max(
                0,
                int(math.ceil(
                    self._deadline - time.monotonic()
                )),
            )

        self.running = False
        self._deadline = None
        self._cancel_android_alarm()
        self.status_label.text = "Stopped"
        log.info("Timer: stopped")
        self.update_display()

    def reset(self, instance):
        self.running = False
        self._deadline = None
        self._cancel_android_alarm()
        self._finished_notified = False
        self.remaining = (
            self.original_seconds
            or self.read_seconds_from_wheels()
        )
        self.status_label.text = "Ready"
        log.info("Timer: reset")
        self.update_display()

    def tick(self, dt):
        if not self.running:
            self.update_display()
            return

        if self._deadline is None:
            self._deadline = time.monotonic() + float(
                max(0, self.remaining)
            )

        self.remaining = max(
            0,
            int(math.ceil(
                self._deadline - time.monotonic()
            )),
        )

        if self.remaining <= 0:
            self.running = False
            self._deadline = None
            self.remaining = 0
            self.status_label.text = "TIME IS UP!"
            log.info("Timer: time is up")

            if not self._finished_notified:
                self._finished_notified = True
                self.notify_time_is_up()

        self.update_display()

    def notify_time_is_up(self):
        """Alert the user even when the Timer screen is not currently open."""
        self._play_finish_sound()

        content = BoxLayout(
            orientation="vertical",
            spacing=height(12),
            padding=height(12),
        )

        message = Label(
            text="TIME IS UP!",
            font_size=timer_time_font(),
            bold=True,
        )

        close_btn = Button(
            text="OK",
            font_size=button_font(),
            size_hint_y=None,
            height=height(58),
        )

        content.add_widget(message)
        content.add_widget(close_btn)

        popup = Popup(
            title="Timer",
            content=content,
            size_hint=(0.82, 0.42),
            auto_dismiss=False,
        )

        close_btn.bind(
            on_press=popup.dismiss
        )

        popup.open()

    def _play_finish_sound(self):
        """Play the timer alert without interfering with Realtime SDL audio."""
        primary = BASE_DIR / "data" / "sounds" / "reminder.wav"
        secondary = BASE_DIR / "data" / "sounds" / "reminder2.wav"

        sound_path = None
        for candidate in (primary, secondary):
            if candidate.exists():
                sound_path = candidate
                break

        if platform == "android":
            # Use Android's native media stack instead of Kivy SoundLoader.
            # Realtime voice already uses SDL for speaker playback, and a
            # second SDL/Kivy sound path can be silent on some Android devices.
            try:
                from jnius import autoclass

                MediaPlayer = autoclass("android.media.MediaPlayer")
                AudioManager = autoclass("android.media.AudioManager")

                if sound_path is not None:
                    player = MediaPlayer()
                    player.setAudioStreamType(
                        AudioManager.STREAM_ALARM
                    )
                    player.setDataSource(
                        str(sound_path)
                    )
                    player.prepare()
                    player.start()

                    # Keep a reference alive until completion.
                    self._android_timer_player = player

                    log.info(
                        "Timer: Android MediaPlayer started "
                        f"{sound_path}"
                    )
                    return

            except Exception as error:
                log.warning(
                    "Timer: Android MediaPlayer failed "
                    f"{type(error).__name__}: {error}"
                )

            # Guaranteed native fallback: play the Android alarm tone.
            try:
                from jnius import autoclass

                RingtoneManager = autoclass(
                    "android.media.RingtoneManager"
                )
                PythonActivity = autoclass(
                    "org.kivy.android.PythonActivity"
                )

                activity = PythonActivity.mActivity
                uri = RingtoneManager.getDefaultUri(
                    RingtoneManager.TYPE_ALARM
                )

                if uri is None:
                    uri = RingtoneManager.getDefaultUri(
                        RingtoneManager.TYPE_NOTIFICATION
                    )

                ringtone = RingtoneManager.getRingtone(
                    activity,
                    uri,
                )

                if ringtone is not None:
                    self._android_timer_ringtone = ringtone
                    ringtone.play()
                    log.info(
                        "Timer: Android default alarm tone started"
                    )
                    return

            except Exception as error:
                log.warning(
                    "Timer: Android alarm-tone fallback failed "
                    f"{type(error).__name__}: {error}"
                )

            log.warning(
                "Timer: Android timer alert could not play sound"
            )
            return

        # Desktop fallback keeps the existing Kivy audio behavior.
        if sound_path is not None:
            try:
                sound = SoundLoader.load(
                    str(sound_path)
                )
                if sound is not None:
                    self._finish_sound = sound
                    sound.play()
                    log.info(
                        f"Timer: notification sound {sound_path}"
                    )
                    return
            except Exception as error:
                log.warning(
                    "Timer: notification sound failed "
                    f"{type(error).__name__}: {error}"
                )

        log.warning(
            "Timer: reminder sound not available; showing popup only"
        )

    def _android_alarm_pending_intent(self):
        """Return the PendingIntent used by the native TimerAlarmReceiver."""
        if platform != "android":
            return None

        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        PendingIntent = autoclass("android.app.PendingIntent")
        Receiver = autoclass("com.m12os.m12os.TimerAlarmReceiver")

        activity = PythonActivity.mActivity
        intent = Intent(activity, Receiver)
        intent.setAction("com.m12os.TIMER_TIME_IS_UP")

        flags = PendingIntent.FLAG_UPDATE_CURRENT
        try:
            flags |= PendingIntent.FLAG_IMMUTABLE
        except Exception:
            pass

        return PendingIntent.getBroadcast(activity, 12053, intent, flags)

    def _schedule_android_alarm(self):
        """Schedule the native Android alarm for the current remaining time."""
        if platform != "android" or self.remaining <= 0:
            return

        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Context = autoclass("android.content.Context")
            AlarmManager = autoclass("android.app.AlarmManager")
            SystemClock = autoclass("android.os.SystemClock")
            BuildVersion = autoclass("android.os.Build$VERSION")

            activity = PythonActivity.mActivity
            alarm_manager = activity.getSystemService(Context.ALARM_SERVICE)
            pending_intent = self._android_alarm_pending_intent()

            trigger_at = (
                SystemClock.elapsedRealtime()
                + int(max(1, self.remaining) * 1000)
            )

            # Android 12+ can require the user-granted "Alarms & reminders"
            # special access before exact alarms are permitted.
            if BuildVersion.SDK_INT >= 31:
                try:
                    if not alarm_manager.canScheduleExactAlarms():
                        log.warning(
                            "Timer: exact alarm access is not enabled; "
                            "using allow-while-idle fallback"
                        )
                        alarm_manager.setAndAllowWhileIdle(
                            AlarmManager.ELAPSED_REALTIME_WAKEUP,
                            trigger_at,
                            pending_intent,
                        )
                        return
                except Exception as error:
                    log.warning(
                        "Timer: exact alarm access check failed "
                        f"{type(error).__name__}: {error}"
                    )

            alarm_manager.setExactAndAllowWhileIdle(
                AlarmManager.ELAPSED_REALTIME_WAKEUP,
                trigger_at,
                pending_intent,
            )
            log.info(
                f"Timer: Android native alarm scheduled "
                f"for {int(self.remaining)} seconds"
            )

        except Exception as error:
            log.warning(
                "Timer: Android native alarm scheduling failed "
                f"{type(error).__name__}: {error}"
            )

    def _cancel_android_alarm(self):
        """Cancel any native Android timer alarm that is still pending."""
        if platform != "android":
            return

        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Context = autoclass("android.content.Context")

            activity = PythonActivity.mActivity
            alarm_manager = activity.getSystemService(Context.ALARM_SERVICE)
            pending_intent = self._android_alarm_pending_intent()

            if pending_intent is not None:
                alarm_manager.cancel(pending_intent)
                pending_intent.cancel()

            log.info("Timer: Android native alarm cancelled")

        except Exception as error:
            log.warning(
                "Timer: Android native alarm cancel failed "
                f"{type(error).__name__}: {error}"
            )

    def update_display(self):
        # When the timer has completed, show true 00:00:00 rather than
        # falling back to the wheel values.
        if self.original_seconds > 0 and self.remaining <= 0:
            total = 0
        else:
            total = (
                self.remaining
                if self.remaining > 0
                else self.read_seconds_from_wheels()
            )

        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60

        self.time_label.text = f"{h:02}:{m:02}:{s:02}"

    def go_back(self, instance=None):
        log.info("Timer: Back pressed")
        self.manager.current = "clock"