from datetime import datetime, timedelta
import zlib

from kivy.utils import platform


ACTION_EVENT_REMINDER = "com.m12os.EVENT_REMINDER"
ACTION_EVENT_TIME = "com.m12os.EVENT_TIME"
ACTION_EVENT_STOP = "com.m12os.EVENT_STOP"

REMINDER_MINUTES = {
    "None": None,
    "Event Time": 0,
    "At event time": 0,
    "At time": 0,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "1 day": 1440,
    "5 minutes before": 5,
    "15 minutes before": 15,
    "30 minutes before": 30,
    "1 hour before": 60,
    "1 day before": 1440,
}


def _event_datetime(event):
    return datetime.strptime(
        f"{event['date']} {event.get('time', '00:00') or '00:00'}",
        "%Y-%m-%d %H:%M",
    )


def _base_request_code(event):
    key = (
        f"{event.get('title', '')}|"
        f"{event.get('date', '')}|"
        f"{event.get('time', '')}"
    )
    # Leave room for +1 (event time) and +2 (early reminder).
    return (zlib.crc32(key.encode("utf-8")) & 0x1FFFFFFF) * 4


def _android_objects():
    from jnius import autoclass

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Context = autoclass("android.content.Context")
    Intent = autoclass("android.content.Intent")
    ComponentName = autoclass("android.content.ComponentName")
    PendingIntent = autoclass("android.app.PendingIntent")
    AlarmManager = autoclass("android.app.AlarmManager")
    VERSION = autoclass("android.os.Build$VERSION")

    activity = PythonActivity.mActivity
    manager = activity.getSystemService(Context.ALARM_SERVICE)
    component = ComponentName(
        activity.getPackageName(),
        "com.m12os.m12os.EventAlarmReceiver",
    )

    return (
        activity,
        manager,
        component,
        Intent,
        PendingIntent,
        AlarmManager,
        VERSION,
    )


def _schedule_one(event, trigger_dt, action, request_code, reminder_text):
    (
        activity,
        manager,
        component,
        Intent,
        PendingIntent,
        AlarmManager,
        VERSION,
    ) = _android_objects()

    if manager is None:
        print("[EventAlarmScheduler] AlarmManager unavailable.")
        return False

    if VERSION.SDK_INT >= 31 and not manager.canScheduleExactAlarms():
        print("[EventAlarmScheduler] Exact alarms are not permitted.")
        return False

    trigger_ms = int(trigger_dt.timestamp() * 1000)
    if trigger_ms <= int(datetime.now().timestamp() * 1000):
        print(
            f"[EventAlarmScheduler] Skipping past {action}: "
            f"{trigger_dt.isoformat()}"
        )
        return False

    intent = Intent()
    intent.setComponent(component)
    intent.setAction(action)
    intent.putExtra("event_title", str(event.get("title", "M12 Event")))
    intent.putExtra("event_notes", str(event.get("notes", "")))
    intent.putExtra(
        "event_datetime",
        f"{event.get('date', '')} {event.get('time', '')}",
    )
    reminder_minutes = REMINDER_MINUTES.get(
        str(reminder_text),
        0,
    )
    if reminder_minutes is None:
        reminder_minutes = 0

    intent.putExtra(
        "event_reminder_minutes",
        int(reminder_minutes),
    )

    flags = PendingIntent.FLAG_UPDATE_CURRENT
    if VERSION.SDK_INT >= 23:
        flags |= PendingIntent.FLAG_IMMUTABLE

    pi = PendingIntent.getBroadcast(
        activity,
        int(request_code),
        intent,
        flags,
    )

    if VERSION.SDK_INT >= 23:
        manager.setExactAndAllowWhileIdle(
            AlarmManager.RTC_WAKEUP,
            trigger_ms,
            pi,
        )
    else:
        manager.setExact(
            AlarmManager.RTC_WAKEUP,
            trigger_ms,
            pi,
        )

    print(
        f"[EventAlarmScheduler] Scheduled {action} for "
        f"{trigger_dt.isoformat()} request={request_code}"
    )
    return True


def schedule_event(event):
    """
    Schedule the exact event-time alert plus the optional early reminder.

    None       -> exact event time only
    Event Time -> exact event time only
    N before   -> N-minutes-before + exact event time
    """
    if platform != "android":
        return False

    try:
        event_dt = _event_datetime(event)
        base = _base_request_code(event)

        event_time_scheduled = _schedule_one(
            event,
            event_dt,
            ACTION_EVENT_TIME,
            base + 1,
            "Event Time",
        )

        reminder = str(event.get("reminder", "None")).strip() or "None"
        minutes = REMINDER_MINUTES.get(reminder)
        reminder_scheduled = False

        if minutes is not None and int(minutes) > 0:
            reminder_dt = event_dt - timedelta(minutes=int(minutes))
            reminder_scheduled = _schedule_one(
                event,
                reminder_dt,
                ACTION_EVENT_REMINDER,
                base + 2,
                reminder,
            )

        return event_time_scheduled or reminder_scheduled

    except Exception as error:
        print(
            "[EventAlarmScheduler] Schedule error: "
            f"{type(error).__name__}: {error}"
        )
        return False


def cancel_event(event):
    if platform != "android":
        return False

    try:
        (
            activity,
            manager,
            component,
            Intent,
            PendingIntent,
            _AlarmManager,
            VERSION,
        ) = _android_objects()

        base = _base_request_code(event)
        flags = PendingIntent.FLAG_UPDATE_CURRENT
        if VERSION.SDK_INT >= 23:
            flags |= PendingIntent.FLAG_IMMUTABLE

        for action, request_code in (
            (ACTION_EVENT_TIME, base + 1),
            (ACTION_EVENT_REMINDER, base + 2),
        ):
            intent = Intent()
            intent.setComponent(component)
            intent.setAction(action)

            pi = PendingIntent.getBroadcast(
                activity,
                int(request_code),
                intent,
                flags,
            )
            manager.cancel(pi)
            pi.cancel()

        print("[EventAlarmScheduler] Event alarms cancelled.")
        return True

    except Exception as error:
        print(
            "[EventAlarmScheduler] Cancel error: "
            f"{type(error).__name__}: {error}"
        )
        return False


def stop_event_sound():
    """Send EVENT_STOP from inside M12 OS when Calendar opens."""
    if platform != "android":
        return False

    try:
        (
            activity,
            _manager,
            component,
            Intent,
            PendingIntent,
            _AlarmManager,
            VERSION,
        ) = _android_objects()

        intent = Intent()
        intent.setComponent(component)
        intent.setAction(ACTION_EVENT_STOP)

        flags = PendingIntent.FLAG_UPDATE_CURRENT
        if VERSION.SDK_INT >= 23:
            flags |= PendingIntent.FLAG_IMMUTABLE

        pi = PendingIntent.getBroadcast(
            activity,
            22999,
            intent,
            flags,
        )
        pi.send()
        print("[EventAlarmScheduler] EVENT_STOP sent.")
        return True

    except Exception as error:
        print(
            "[EventAlarmScheduler] Stop error: "
            f"{type(error).__name__}: {error}"
        )
        return False