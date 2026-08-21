from datetime import datetime, timedelta

from kivy.utils import platform


DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
REQUEST_BASE = 31000
MAX_NATIVE_ALARMS = 200


def _next_occurrence(alarm, now=None):
    if now is None:
        now = datetime.now()

    if not bool(alarm.get("enabled", False)):
        return None

    try:
        hour = int(alarm.get("hour", 0))
        minute = int(alarm.get("minute", 0))
    except (TypeError, ValueError):
        return None

    repeat_mode = str(alarm.get("repeat_mode","once")).strip()
    days = list(alarm.get("days", []))
    until_text = str(alarm.get("until_date", "")).strip()

    until_date = None
    if until_text:
        try:
            until_date = datetime.strptime(
                until_text,
                "%Y-%m-%d",
            ).date()
        except ValueError:
            until_date = None

    # Look ahead far enough for all supported repeat modes.
    for offset in range(0, 370):
        target_date = now.date() + timedelta(days=offset)

        if until_date is not None and target_date > until_date:
            return None

        if repeat_mode == "every_day":
            allowed = True
        elif repeat_mode == "days":
            allowed = DAY_NAMES[target_date.weekday()] in days
        else:
            # "once": the next occurrence is today if still in the future,
            # otherwise tomorrow.
            allowed = True

        if not allowed:
            continue

        candidate = datetime.combine(
            target_date,
            datetime.min.time(),
        ).replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        if candidate <= now:
            if repeat_mode == "once":
                # A clock alarm with no explicit date means the next time that
                # clock time occurs, which is tomorrow when today's time passed.
                if offset == 0:
                    continue
            else:
                continue

        return candidate

    return None


def _android_classes():
    from jnius import autoclass

    return {
        "PythonActivity": autoclass(
            "org.kivy.android.PythonActivity"
        ),
        "Context": autoclass(
            "android.content.Context"
        ),
        "Intent": autoclass(
            "android.content.Intent"
        ),
        "PendingIntent": autoclass(
            "android.app.PendingIntent"
        ),
        "AlarmManager": autoclass(
            "android.app.AlarmManager"
        ),
        "Bundle": autoclass(
            "android.os.Bundle"
        ),
        "VERSION": autoclass(
            "android.os.Build$VERSION"
        ),
    }


def _pending_intent(
    activity,
    request_code,
    alarm=None,
):
    c = _android_classes()
    Intent = c["Intent"]
    PendingIntent = c["PendingIntent"]
    VERSION = c["VERSION"]

    from jnius import autoclass
    ComponentName = autoclass(
        "android.content.ComponentName"
    )

    intent = Intent()

    # Avoid Intent.setClassName(Context, String) here.
    # PyJNIus can select the String/String overload and then reject
    # PythonActivity as a Java String. An explicit ComponentName removes
    # that overload ambiguity.
    component = ComponentName(
        activity.getPackageName(),
        "com.m12os.m12os.ClockAlarmReceiver",
    )
    intent.setComponent(
        component
    )
    intent.setAction(
        "com.m12os.CLOCK_ALARM_RING"
    )

    if alarm is not None:
        Bundle = c["Bundle"]
        extras = Bundle()

        extras.putInt(
            "request_code",
            int(request_code),
        )
        extras.putInt(
            "alarm_hour",
            int(alarm.get("hour", 0)),
        )
        extras.putInt(
            "alarm_minute",
            int(alarm.get("minute", 0)),
        )
        extras.putString(
            "alarm_name",
            str(alarm.get("name", "")),
        )
        extras.putString(
            "repeat_mode",
            str(alarm.get("repeat_mode", "once")),
        )
        extras.putString(
            "days",
            ",".join(
                str(item)
                for item in alarm.get("days", [])
            ),
        )
        extras.putString(
            "until_date",
            str(alarm.get("until_date", "")),
        )

        intent.putExtras(extras)

    flags = PendingIntent.FLAG_UPDATE_CURRENT
    if VERSION.SDK_INT >= 23:
        flags |= PendingIntent.FLAG_IMMUTABLE

    return PendingIntent.getBroadcast(
        activity,
        int(request_code),
        intent,
        flags,
    )


def cancel_all_android_clock_alarms():
    if platform != "android":
        return False

    try:
        c = _android_classes()
        activity = c["PythonActivity"].mActivity
        manager = activity.getSystemService(
            c["Context"].ALARM_SERVICE
        )

        for offset in range(MAX_NATIVE_ALARMS):
            request_code = REQUEST_BASE + offset
            pi = _pending_intent(
                activity,
                request_code,
            )
            manager.cancel(pi)
            pi.cancel()

        print(
            "[ClockAlarmScheduler] Cleared native clock alarms."
        )
        return True

    except Exception as error:
        print(
            "[ClockAlarmScheduler] Cancel error: "
            f"{type(error).__name__}: {error}"
        )
        return False


def sync_android_clock_alarms(alarms):
    """
    Rebuild every native Clock alarm from the current alarms.json model.

    Desktop/Linux/macOS: no-op.
    Android: cancel the managed PendingIntent range, then schedule the next
    occurrence of every enabled Clock alarm using exact RTC_WAKEUP alarms.
    """
    if platform != "android":
        return False

    try:
        c = _android_classes()
        activity = c["PythonActivity"].mActivity
        manager = activity.getSystemService(
            c["Context"].ALARM_SERVICE
        )
        AlarmManager = c["AlarmManager"]
        VERSION = c["VERSION"]

        # Remove stale alarms left by edits/deletes.
        cancel_all_android_clock_alarms()

        if VERSION.SDK_INT >= 31:
            if not manager.canScheduleExactAlarms():
                print(
                    "[ClockAlarmScheduler] Exact alarms are not permitted."
                )
                return False

        scheduled = 0
        now = datetime.now()

        for index, alarm in enumerate(
            list(alarms)[:MAX_NATIVE_ALARMS]
        ):
            next_dt = _next_occurrence(
                alarm,
                now=now,
            )

            if next_dt is None:
                continue

            request_code = REQUEST_BASE + index
            pi = _pending_intent(
                activity,
                request_code,
                alarm=alarm,
            )

            trigger_ms = int(
                next_dt.timestamp() * 1000
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

            scheduled += 1
            print(
                "[ClockAlarmScheduler] Scheduled "
                f"{request_code} for {next_dt.isoformat()} "
                f"repeat={alarm.get('repeat_mode', 'once')}"
            )

        print(
            "[ClockAlarmScheduler] Ready: "
            f"{scheduled} native alarm(s)."
        )
        return True

    except Exception as error:
        print(
            "[ClockAlarmScheduler] Sync error:"
            f"{type(error).__name__}: {error}"
        )
        return False