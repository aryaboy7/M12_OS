# Not Used yet in the project- calculation is done in the screens separatly.
from datetime import datetime


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def parse_event_datetime(event):
    try:
        date_text = str(event.get("date", "")).strip()
        time_text = str(event.get("time", "")).strip() or "00:00"
        return datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")
    except Exception:
        return None


def is_event_active_today(event, now=None):
    if now is None:
        now = datetime.now()

    event_dt = parse_event_datetime(event)

    if not event_dt:
        return False

    today = now.date()
    today_name = DAY_NAMES[today.weekday()]

    repeat_mode = event.get("repeat_mode", "once")
    until_date = str(event.get("until_date", "")).strip()

    if until_date:
        try:
            until = datetime.strptime(until_date, "%Y-%m-%d").date()
            if today > until:
                return False
        except Exception:
            pass

    if repeat_mode == "once":
        return event_dt.date() == today

    if repeat_mode == "every_day":
        return today >= event_dt.date()

    if repeat_mode == "days":
        days = event.get("days", [])
        return today >= event_dt.date() and today_name in days

    return False


def count_active_events_today(events):
    return sum(1 for event in events if is_event_active_today(event))