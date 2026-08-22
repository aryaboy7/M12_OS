import zlib
from datetime import datetime, timedelta

from kivy.utils import platform


REMINDER_MINUTES = {
    "None": None,
    "Event Time": 0,
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

DAY_NAMES = (
    "Mon",
    "Tue",
    "Wed",
    "Thu",
    "Fri",
    "Sat",
    "Sun",
)

ACTION_EVENT_REMINDER = "com.m12os.EVENT_REMINDER"
ACTION_EVENT_TIME = "com.m12os.EVENT_TIME"
ACTION_EVENT_STOP = "com.m12os.EVENT_STOP"
RECEIVER_CLASS = "com.m12os.m12os.EventAlarmReceiver"

REQUEST_BASE = 220000
MAX_EVENT_SLOTS = 1000


def _android_classes():
    from jnius import autoclass

    return {
        "PythonActivity": autoclass("org.kivy.android.PythonActivity"),
        "Context": autoclass("android.content.Context"),
        "Intent": autoclass("android.content.Intent"),
        "ComponentName": autoclass("android.content.ComponentName"),
        "PendingIntent": autoclass("android.app.PendingIntent"),
        "AlarmManager": autoclass("android.app.AlarmManager"),
        "VERSION": autoclass("android.os.Build$VERSION"),
    }


def _parse_event_datetime(event):
    try:
        date_text = str(event.get("date", "")).strip()
        time_text = str(event.get("time", "")).strip() or "00:00"
        return datetime.strptime(
            f"{date_text} {time_text}",
            "%Y-%m-%d %H:%M",
        )
    except Exception:
        return None


def _until_date(event):
    text = str(event.get("until_date", "")).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return None


def _next_occurrence(event, now=None):
    if now is None:
        now = datetime.now()

    base_dt = _parse_event_datetime(event)
    if base_dt is None:
        return None

    repeat_mode = str(event.get("repeat_mode", "once")).strip() or "once"

    if repeat_mode == "once":
        return base_dt if base_dt > now else None

    until = _until_date(event)
    start_date = max(now.date(), base_dt.date())

    for offset in range(0, 370):
        day = start_date + timedelta(days=offset)

        if until is not None and day > until:
            return None

        candidate = datetime.combine(day, base_dt.time())

        if candidate <= now:
            continue

        if repeat_mode == "every_day":
            return candidate

        if repeat_mode == "days":
            allowed = event.get("days", [])
            if not isinstance(allowed, list):
                allowed = []

            if DAY_NAMES[candidate.weekday()] in allowed:
                return candidate

    return None


def _normalize_reminder(value):
    text = str(value or "None").strip() or "None"

    aliases = {
        "At event time": "Event Time",
        "At time": "Event Time",
        "5 minutes before": "5m",
        "15 minutes before": "15m",
        "30 minutes before": "30m",
        "1 hour before": "1h",
        "1 day before": "1 day",
    }

    return aliases.get(text, text)


def _request_codes(index):
    base = REQUEST_BASE + (int(index) * 2)
    return base, base + 1


def _pending_intent(
    activity,
    classes,
    event,
    action,
    request_code,
):
    Intent = classes["Intent"]
    ComponentName = classes["ComponentName"]
    PendingIntent = classes["PendingIntent"]
    VERSION = classes["VERSION"]

    component = ComponentName(
        activity.getPackageName(),
        RECEIVER_CLASS,
    )

    intent = Intent()
    intent.setComponent(component)
    intent.setAction(action)

    intent.putExtra(
        "event_title",
        str(event.get("title", "M12 Event")),
    )
    intent.putExtra(
        "event_notes",
        str(event.get("notes", "")),
    )
    intent.putExtra(
        "event_datetime",
        f"{event.get('date', '')} {event.get('time', '')}",
    )
    intent.putExtra(
        "event_reminder",
        _normalize_reminder(event.get("reminder", "None")),
    )

    flags = PendingIntent.FLAG_UPDATE_CURRENT
    if VERSION.SDK_INT >= 23:
        flags |= PendingIntent.FLAG_IMMUTABLE

    return PendingIntent.getBroadcast(
        activity,
        int(request_code),
        intent,
        flags,
    )


def _schedule_exact(manager, classes, trigger_dt, pending_intent):
    AlarmManager = classes["AlarmManager"]
    VERSION = classes["VERSION"]

    trigger_ms = int(trigger_dt.timestamp() * 1000)

    if VERSION.SDK_INT >= 23:
        manager.setExactAndAllowWhileIdle(
            AlarmManager.RTC_WAKEUP,
            trigger_ms,
            pending_intent,
        )
    else:
        manager.setExact(
            AlarmManager.RTC_WAKEUP,
            trigger_ms,
            pending_intent,
        )


def _cancel_pending(manager, classes, activity, event, action, request_code):
    try:
        pi = _pending_intent(
            activity,
            classes,
            event,
            action,
            request_code,
        )
        manager.cancel(pi)
        pi.cancel()
    except Exception:
        pass


def schedule_android_event(event, index=0):
    """
    Schedule the next native Android occurrence for one event.

    Every event gets EVENT_TIME at the exact event time.

    When the event reminder is N minutes before, EVENT_REMINDER is also
    scheduled at event time minus N minutes.

    Reminder == Event Time -> only EVENT_TIME.
    Reminder == None       -> only EVENT_TIME.
    """
    if platform != "android":
        return False

    try:
        classes = _android_classes()
        PythonActivity = classes["PythonActivity"]
        Context = classes["Context"]
        VERSION = classes["VERSION"]

        activity = PythonActivity.mActivity
        manager = activity.getSystemService(Context.ALARM_SERVICE)

        if manager is None:
            print("[EventAlarmScheduler] AlarmManager unavailable.")
            return False

        if VERSION.SDK_INT >= 31 and not manager.canScheduleExactAlarms():
            print("[EventAlarmScheduler] Exact alarms are not permitted.")
            return False

        occurrence = _next_occurrence(event)
        if occurrence is None:
            return False

        reminder_code, time_code = _request_codes(index)

        # Exact event-time alert is always scheduled.
        event_time_pi = _pending_intent(
            activity,
            classes,
            event,
            ACTION_EVENT_TIME,
            time_code,
        )
        _schedule_exact(
            manager,
            classes,
            occurrence,
            event_time_pi,
        )

        print(
            "[EventAlarmScheduler] Scheduled EVENT_TIME "
            f"for {occurrence.isoformat()} request={time_code}"
        )

        reminder = _normalize_reminder(
            event.get("reminder", "None")
        )
        minutes = REMINDER_MINUTES.get(reminder)

        if (
            reminder not in ("None", "Event Time")
            and minutes is not None
            and int(minutes) > 0
        ):
            reminder_dt = occurrence - timedelta(minutes=int(minutes))

            if reminder_dt > datetime.now():
                reminder_pi = _pending_intent(
                    activity,
                    classes,
                    event,
                    ACTION_EVENT_REMINDER,
                    reminder_code,
                )
                _schedule_exact(
                    manager,
                    classes,
                    reminder_dt,
                    reminder_pi,
                )

                print(
                    "[EventAlarmScheduler] Scheduled EVENT_REMINDER "
                    f"for {reminder_dt.isoformat()} "
                    f"({reminder}) request={reminder_code}"
                )

        return True

    except Exception as error:
        print(
            "[EventAlarmScheduler] Schedule error: "
            f"{type(error).__name__}: {error}"
        )
        return False


def sync_android_event_alarms(events):
    """
    Rebuild native Android Calendar alarms from the complete events list.

    The stable request-code scheme is index based, so edits/deletes are
    handled by canceling the supported slots before rescheduling.
    """
    if platform != "android":
        return False

    try:
        classes = _android_classes()
        PythonActivity = classes["PythonActivity"]
        Context = classes["Context"]
        PendingIntent = classes["PendingIntent"]
        Intent = classes["Intent"]
        ComponentName = classes["ComponentName"]
        VERSION = classes["VERSION"]

        activity = PythonActivity.mActivity
        manager = activity.getSystemService(Context.ALARM_SERVICE)

        if manager is None:
            return False

        component = ComponentName(
            activity.getPackageName(),
            RECEIVER_CLASS,
        )

        flags = PendingIntent.FLAG_NO_CREATE
        if VERSION.SDK_INT >= 23:
            flags |= PendingIntent.FLAG_IMMUTABLE

        # Cancel only PendingIntents that already exist; this does not create
        # hundreds of new PendingIntents while cleaning stale event slots.
        for index in range(MAX_EVENT_SLOTS):
            reminder_code, time_code = _request_codes(index)

            for action, code in (
                (ACTION_EVENT_REMINDER, reminder_code),
                (ACTION_EVENT_TIME, time_code),
            ):
                intent = Intent()
                intent.setComponent(component)
                intent.setAction(action)

                pi = PendingIntent.getBroadcast(
                    activity,
                    int(code),
                    intent,
                    flags,
                )

                if pi is not None:
                    try:
                        manager.cancel(pi)
                        pi.cancel()
                    except Exception:
                        pass

        scheduled = 0

        for index, event in enumerate(list(events or [])):
            if index >= MAX_EVENT_SLOTS:
                break

            if schedule_android_event(event, index=index):
                scheduled += 1

        print(
            "[EventAlarmScheduler] Ready: "
            f"{scheduled} event(s) scheduled natively."
        )

        return True

    except Exception as error:
        print(
            "[EventAlarmScheduler] Sync error: "
            f"{type(error).__name__}: {error}"
        )
        return False


def stop_native_event_sound():
    """Stop native EventAlarmReceiver sound when Calendar is opened."""
    if platform != "android":
        return False

    try:
        classes = _android_classes()
        PythonActivity = classes["PythonActivity"]
        Intent = classes["Intent"]
        ComponentName = classes["ComponentName"]

        activity = PythonActivity.mActivity

        component = ComponentName(
            activity.getPackageName(),
            RECEIVER_CLASS,
        )

        intent = Intent()
        intent.setComponent(component)
        intent.setAction(ACTION_EVENT_STOP)

        activity.sendBroadcast(intent)

        print("[EventAlarmScheduler] EVENT_STOP sent.")
        return True

    except Exception as error:
        print(
            "[EventAlarmScheduler] Stop error: "
            f"{type(error).__name__}: {error}"
        )
        return False