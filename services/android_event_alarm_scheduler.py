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

REPEAT_ONCE = 0
REPEAT_EVERY_DAY = 1
REPEAT_DAYS = 2

DAY_BITS = {
    "Mon": 1 << 0,
    "Tue": 1 << 1,
    "Wed": 1 << 2,
    "Thu": 1 << 3,
    "Fri": 1 << 4,
    "Sat": 1 << 5,
    "Sun": 1 << 6,
}


def _base_datetime(event):
    return datetime.strptime(
        f"{event['date']} {event.get('time', '00:00') or '00:00'}",
        "%Y-%m-%d %H:%M",
    )


def _repeat_type(event):
    mode = str(event.get("repeat_mode", "once")).strip()

    if mode == "every_day":
        return REPEAT_EVERY_DAY

    if mode == "days":
        return REPEAT_DAYS

    return REPEAT_ONCE


def _days_mask(event):
    mask = 0

    days = event.get("days", [])
    if not isinstance(days, list):
        return 0

    for day in days:
        mask |= DAY_BITS.get(str(day).strip(), 0)

    return int(mask)


def _until_ymd(event):
    value = str(event.get("until_date", "")).strip()

    if not value:
        return 0

    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
        return dt.year * 10000 + dt.month * 100 + dt.day
    except Exception:
        return 0


def _next_occurrence(event, now=None):
    if now is None:
        now = datetime.now()

    base = _base_datetime(event)
    repeat_type = _repeat_type(event)
    until_ymd = _until_ymd(event)

    if repeat_type == REPEAT_ONCE:
        return base if base > now else None

    start_date = max(base.date(), now.date())
    days_mask = _days_mask(event)

    for offset in range(0, 371):
        candidate_date = start_date + timedelta(days=offset)

        candidate_ymd = (
            candidate_date.year * 10000
            + candidate_date.month * 100
            + candidate_date.day
        )

        if until_ymd and candidate_ymd > until_ymd:
            return None

        if repeat_type == REPEAT_DAYS:
            bit = 1 << candidate_date.weekday()

            if not (days_mask & bit):
                continue

        candidate = datetime.combine(
            candidate_date,
            base.time(),
        )

        if candidate > now:
            return candidate

    return None


def _base_request_code(event):
    key = (
        f"{event.get('title', '')}|"
        f"{event.get('date', '')}|"
        f"{event.get('time', '')}"
    )

    return (
        zlib.crc32(key.encode("utf-8"))
        & 0x1FFFFFFF
    ) * 4


def _android_objects():
    from jnius import autoclass

    PythonActivity = autoclass(
        "org.kivy.android.PythonActivity"
    )
    Context = autoclass(
        "android.content.Context"
    )
    Intent = autoclass(
        "android.content.Intent"
    )
    ComponentName = autoclass(
        "android.content.ComponentName"
    )
    PendingIntent = autoclass(
        "android.app.PendingIntent"
    )
    AlarmManager = autoclass(
        "android.app.AlarmManager"
    )
    Bundle = autoclass(
        "android.os.Bundle"
    )
    VERSION = autoclass(
        "android.os.Build$VERSION"
    )

    activity = PythonActivity.mActivity

    manager = activity.getSystemService(
        Context.ALARM_SERVICE
    )

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
        Bundle,
        VERSION,
    )


def _put_common_extras(
    intent,
    event,
    occurrence_dt,
    reminder_minutes,
    base_request_code,
    Bundle,
):
    """
    Put extras into a real Android Bundle using explicit Java types.

    This avoids PyJNIus choosing Intent.putExtra overloads such as
    Short or char[] instead of int/String.
    """
    bundle = Bundle()

    bundle.putString(
        "event_title",
        str(event.get("title", "M12 Event")),
    )

    bundle.putString(
        "event_notes",
        str(event.get("notes", "")),
    )

    bundle.putString(
        "event_datetime",
        occurrence_dt.strftime(
            "%Y-%m-%d %H:%M"
        ),
    )

    bundle.putLong(
        "event_occurrence_ms",
        int(
            occurrence_dt.timestamp()
            * 1000
        ),
    )

    bundle.putInt(
        "event_reminder_minutes",
        int(reminder_minutes),
    )

    bundle.putInt(
        "event_repeat_type",
        int(_repeat_type(event)),
    )

    bundle.putInt(
        "event_days_mask",
        int(_days_mask(event)),
    )

    bundle.putInt(
        "event_until_ymd",
        int(_until_ymd(event)),
    )

    bundle.putInt(
        "event_hour",
        int(occurrence_dt.hour),
    )

    bundle.putInt(
        "event_minute",
        int(occurrence_dt.minute),
    )

    bundle.putInt(
        "event_request_code_base",
        int(base_request_code),
    )

    intent.putExtras(bundle)


def _schedule_one(
    event,
    occurrence_dt,
    trigger_dt,
    action,
    request_code,
    reminder_minutes,
    base_request_code,
):
    (
        activity,
        manager,
        component,
        Intent,
        PendingIntent,
        AlarmManager,
        Bundle,
        VERSION,
    ) = _android_objects()

    if manager is None:
        print(
            "[EventAlarmScheduler] "
            "AlarmManager unavailable."
        )
        return False

    if (
        VERSION.SDK_INT >= 31
        and not manager.canScheduleExactAlarms()
    ):
        print(
            "[EventAlarmScheduler] "
            "Exact alarms are not permitted."
        )
        return False

    trigger_ms = int(
        trigger_dt.timestamp()
        * 1000
    )

    now_ms = int(
        datetime.now().timestamp()
        * 1000
    )

    if trigger_ms <= now_ms:
        print(
            "[EventAlarmScheduler] "
            f"Skipping past {action}: "
            f"{trigger_dt.isoformat()}"
        )
        return False

    intent = Intent()
    intent.setComponent(component)
    intent.setAction(action)

    _put_common_extras(
        intent,
        event,
        occurrence_dt,
        reminder_minutes,
        base_request_code,
        Bundle,
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
        "[EventAlarmScheduler] "
        f"Scheduled {action} for "
        f"{trigger_dt.isoformat()} "
        f"repeat_type={_repeat_type(event)} "
        f"days_mask={_days_mask(event)} "
        f"until={_until_ymd(event)}"
    )

    return True


def schedule_event(event):
    if platform != "android":
        return False

    try:
        occurrence_dt = _next_occurrence(
            event
        )

        if occurrence_dt is None:
            print(
                "[EventAlarmScheduler] "
                "No future occurrence."
            )
            return False

        base_request_code = (
            _base_request_code(event)
        )

        reminder = str(
            event.get(
                "reminder",
                "None",
            )
        ).strip() or "None"

        minutes = REMINDER_MINUTES.get(
            reminder
        )

        if minutes is None:
            reminder_minutes = 0
            schedule_early = False
        else:
            reminder_minutes = int(minutes)
            schedule_early = (
                reminder_minutes > 0
            )

        event_time_scheduled = (
            _schedule_one(
                event=event,
                occurrence_dt=occurrence_dt,
                trigger_dt=occurrence_dt,
                action=ACTION_EVENT_TIME,
                request_code=(
                    base_request_code + 1
                ),
                reminder_minutes=(
                    reminder_minutes
                ),
                base_request_code=(
                    base_request_code
                ),
            )
        )

        reminder_scheduled = False

        if schedule_early:
            reminder_dt = (
                occurrence_dt
                - timedelta(
                    minutes=(
                        reminder_minutes
                    )
                )
            )

            reminder_scheduled = (
                _schedule_one(
                    event=event,
                    occurrence_dt=(
                        occurrence_dt
                    ),
                    trigger_dt=(
                        reminder_dt
                    ),
                    action=(
                        ACTION_EVENT_REMINDER
                    ),
                    request_code=(
                        base_request_code
                        + 2
                    ),
                    reminder_minutes=(
                        reminder_minutes
                    ),
                    base_request_code=(
                        base_request_code
                    ),
                )
            )

        return (
            event_time_scheduled
            or reminder_scheduled
        )

    except Exception as error:
        print(
            "[EventAlarmScheduler] "
            "Schedule error: "
            f"{type(error).__name__}: "
            f"{error}"
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
            _Bundle,
            VERSION,
        ) = _android_objects()

        base = _base_request_code(
            event
        )

        flags = (
            PendingIntent.FLAG_UPDATE_CURRENT
        )

        if VERSION.SDK_INT >= 23:
            flags |= (
                PendingIntent.FLAG_IMMUTABLE
            )

        for action, request_code in (
            (
                ACTION_EVENT_TIME,
                base + 1,
            ),
            (
                ACTION_EVENT_REMINDER,
                base + 2,
            ),
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

        print(
            "[EventAlarmScheduler] "
            "Event alarms cancelled."
        )
        return True

    except Exception as error:
        print(
            "[EventAlarmScheduler] "
            "Cancel error: "
            f"{type(error).__name__}: "
            f"{error}"
        )
        return False


def stop_event_sound():
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
            _Bundle,
            VERSION,
        ) = _android_objects()

        intent = Intent()
        intent.setComponent(component)
        intent.setAction(
            ACTION_EVENT_STOP
        )

        flags = (
            PendingIntent.FLAG_UPDATE_CURRENT
        )

        if VERSION.SDK_INT >= 23:
            flags |= (
                PendingIntent.FLAG_IMMUTABLE
            )

        pi = PendingIntent.getBroadcast(
            activity,
            22999,
            intent,
            flags,
        )

        pi.send()

        print(
            "[EventAlarmScheduler] "
            "EVENT_STOP sent."
        )
        return True

    except Exception as error:
        print(
            "[EventAlarmScheduler] "
            "Stop error: "
            f"{type(error).__name__}: "
            f"{error}"
        )
        return False