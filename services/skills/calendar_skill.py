import json
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from services.skills.base_skill import BaseSkill, SkillResult

from kivy.utils import platform

try:
    from services.android_event_alarm_scheduler import (
        schedule_event as schedule_android_event,
    )
except Exception:
    schedule_android_event = None


BASE_DIR = Path(__file__).resolve().parent.parent.parent
from utils.data_paths import EVENTS_FILE

DAY_NAMES = (
    "Mon",
    "Tue",
    "Wed",
    "Thu",
    "Fri",
    "Sat",
    "Sun",
)

REMINDER_MINUTES = {
    "None": None,
    "Event Time": 0,
    "5 minutes before": 5,
    "15 minutes before": 15,
    "30 minutes before": 30,
    "1 hour before": 60,
    "1 day before": 1440,
}


class CalendarSkill(BaseSkill):
    """
    Answer questions about M12OS calendar events.

    Supported examples:
        What events do I have?
        What events do I have today?
        What is on my calendar tomorrow?
        What is my next event?
        What events do I have this week?
        Open calendar.

        Какие у меня события?
        Какие события сегодня?
        Что у меня завтра?
        Какое следующее событие?
        Открой календарь.
    """

    name = "calendar"
    priority = 10

    def __init__(self):
        self._pending_lock = threading.RLock()
        self._pending_event = None


    CREATE_PREFIXES = (
        "create an event", "create event", "add an event", "add event",
        "create an appointment", "create appointment", "add appointment",
        "create a meeting", "create meeting", "add meeting",
        "создай событие", "добавь событие", "создай встречу", "добавь встречу",
    )

    CANCEL_CREATE_PHRASES = {
        "cancel", "cancel event", "never mind", "forget it",
        "отмена", "отмени", "отмени событие", "не надо",
    }

    OPEN_PHRASES = {
        "open calendar",
        "show calendar",
        "go to calendar",
        "calendar app",
        "открой календарь",
        "покажи календарь",
        "перейди в календарь",
    }

    NEXT_PHRASES = {
        "what is my next event",
        "what's my next event",
        "what event is next",
        "next event",
        "when is my next event",
        "what is next on my calendar",
        "какое следующее событие",
        "что у меня следующее",
        "когда мое следующее событие",
        "когда моё следующее событие",
    }

    TODAY_HINTS = (
        "today",
        "today's",
        "сегодня",
    )

    TOMORROW_HINTS = (
        "tomorrow",
        "завтра",
    )

    WEEK_HINTS = (
        "this week",
        "next 7 days",
        "coming week",
        "на этой неделе",
        "ближайшие 7 дней",
    )

    CALENDAR_WORDS = {
        "calendar",
        "calendars",
        "event",
        "events",
        "appointment",
        "appointments",
        "meeting",
        "meetings",
        "schedule",
        "календарь",
        "календаре",
        "событие",
        "события",
        "встреча",
        "встречи",
        "расписание",
    }

    QUERY_PHRASES = {
        "what event i have",
        "what events i have",
        "what event do i have",
        "what events do i have",
        "do i have any events",
        "do i have an event",
        "what is on my calendar",
        "what's on my calendar",
        "show my events",
        "show events",
        "my events",
        "my schedule",
        "any events",
        "какие у меня события",
        "какое у меня событие",
        "есть ли у меня события",
        "что у меня в календаре",
        "покажи мои события",
        "мои события",
        "мое расписание",
        "моё расписание",
    }

    def can_handle(
        self,
        message: str,
        context: Any,
    ) -> float:
        text = self._normalize(message)

        if not text:
            return 0.0

        if self._has_pending_event():
            return 1.0

        if text.startswith(self.CREATE_PREFIXES):
            return 1.0

        if text in self.OPEN_PHRASES:
            return 1.0

        if text in self.NEXT_PHRASES:
            return 1.0

        if text in self.QUERY_PHRASES:
            return 0.99

        words = set(text.split())

        if words.intersection(self.CALENDAR_WORDS):
            if any(
                phrase in text
                for phrase in (
                    *self.TODAY_HINTS,
                    *self.TOMORROW_HINTS,
                    *self.WEEK_HINTS,
                )
            ):
                return 0.99

            if text.startswith(
                (
                    "what ",
                    "which ",
                    "when ",
                    "show ",
                    "do i ",
                    "are there ",
                    "какие ",
                    "какое ",
                    "когда ",
                    "что ",
                    "покажи ",
                    "есть ли ",
                )
            ):
                return 0.96

        return 0.0

    def handle(
        self,
        message: str,
        context: Any,
    ) -> SkillResult:
        text = self._normalize(message)
        russian = self._is_russian(text)

        if self._has_pending_event():
            return self._handle_pending_event(
                original_message=str(message).strip(),
                normalized=text,
                context=context,
                russian=russian,
            )

        if text.startswith(self.CREATE_PREFIXES):
            return self._handle_create_event(
                original_message=str(message).strip(),
                normalized=text,
                context=context,
                russian=russian,
            )

        if text in self.OPEN_PHRASES:
            opened = self._open_calendar(context)

            if opened:
                answer = (
                    "Календарь открыт."
                    if russian
                    else "Calendar opened."
                )
            else:
                answer = (
                    "Не удалось открыть календарь."
                    if russian
                    else "I couldn't open the calendar."
                )

            return SkillResult(
                handled=True,
                answer=answer,
                confidence=1.0,
                action="open_calendar",
                data={"opened": opened},
            )

        events = self._load_events()
        now = datetime.now()

        if text in self.NEXT_PHRASES:
            upcoming = self._occurrences_between(
                events=events,
                start=now,
                end=now + timedelta(days=370),
                limit=1,
            )
            return self._build_result(
                occurrences=upcoming,
                period="next",
                russian=russian,
                confidence=1.0,
            )

        if any(hint in text for hint in self.TOMORROW_HINTS):
            target = now.date() + timedelta(days=1)
            start = datetime.combine(target, datetime.min.time())
            end = start + timedelta(days=1)
            period = "tomorrow"

        elif any(hint in text for hint in self.WEEK_HINTS):
            start = now
            end = now + timedelta(days=7)
            period = "week"

        else:
            # Unqualified calendar questions default to the remainder of today.
            start = now
            end = datetime.combine(
                now.date() + timedelta(days=1),
                datetime.min.time(),
            )
            period = "today"

        occurrences = self._occurrences_between(
            events=events,
            start=start,
            end=end,
            limit=20,
        )

        return self._build_result(
            occurrences=occurrences,
            period=period,
            russian=russian,
            confidence=0.99,
        )

    def _handle_create_event(self, original_message, normalized, context, russian):
        now = datetime.now()
        title = self._extract_event_title(original_message, normalized)
        with self._pending_lock:
            self._pending_event = {
                "title": title,
                "date": self._parse_event_date(normalized, now),
                "time": self._parse_event_time(normalized),
                "notes": None,
                "reminder": None,
                "step": "",
            }
        return self._continue_pending_event(context, russian)

    def _has_pending_event(self):
        with self._pending_lock:
            return self._pending_event is not None

    def _handle_pending_event(self, original_message, normalized, context, russian):
        if normalized in self.CANCEL_CREATE_PHRASES:
            with self._pending_lock:
                self._pending_event = None
            return SkillResult(
                handled=True,
                answer="Создание события отменено." if russian else "Event creation cancelled.",
                confidence=1.0,
                action="calendar_create_cancelled",
            )

        with self._pending_lock:
            if self._pending_event is None:
                return SkillResult(handled=False)
            step = self._pending_event.get("step", "")

        if step == "title":
            value = str(original_message).strip(" .,:;-")
            if not value:
                return self._creation_prompt("title", russian)
            with self._pending_lock:
                self._pending_event["title"] = value

        elif step == "date":
            value = self._parse_event_date(normalized, datetime.now())
            if value is None:
                return self._creation_prompt("date", russian)
            with self._pending_lock:
                self._pending_event["date"] = value

        elif step == "time":
            value = self._parse_event_time(normalized)
            if value is None:
                return self._creation_prompt("time", russian)
            with self._pending_lock:
                self._pending_event["time"] = value

        elif step == "description":
            value = str(original_message).strip()
            if normalized in {"none", "no description", "skip", "без описания", "нет описания"}:
                value = ""
            with self._pending_lock:
                self._pending_event["notes"] = value

        elif step == "reminder":
            value = self._parse_reminder(normalized)
            if value is None:
                return self._creation_prompt("reminder", russian)
            with self._pending_lock:
                self._pending_event["reminder"] = value

        return self._continue_pending_event(context, russian)

    def _continue_pending_event(self, context, russian):
        with self._pending_lock:
            pending = dict(self._pending_event or {})

        if not pending.get("title"):
            step = "title"
        elif pending.get("date") is None:
            step = "date"
        elif pending.get("time") is None:
            step = "time"
        elif pending.get("notes") is None:
            step = "description"
        elif pending.get("reminder") is None:
            step = "reminder"
        else:
            with self._pending_lock:
                finished = dict(self._pending_event)
                self._pending_event = None
            return self._save_created_event(
                title=finished["title"],
                target_date=finished["date"],
                target_time=finished["time"],
                notes=finished["notes"],
                reminder=finished["reminder"],
                context=context,
                russian=russian,
            )

        with self._pending_lock:
            self._pending_event["step"] = step
        return self._creation_prompt(step, russian)

    @staticmethod
    def _creation_prompt(step, russian):
        en = {
            "title": "What is the event name?",
            "date": "What day is the event?",
            "time": "What time is the event?",
            "description": "What is the event description? Say No description if you do not need one.",
            "reminder": "When should I notify you? Say At event time, 5 minutes before, 15 minutes before, 30 minutes before, 1 hour before, 1 day before, or No notification.",
        }
        ru = {
            "title": "Как называется событие?",
            "date": "На какой день событие?",
            "time": "На какое время событие?",
            "description": "Какое описание события? Скажите «Без описания», если оно не нужно.",
            "reminder": "Когда вас уведомить? Скажите: во время события, за 5, 15 или 30 минут, за 1 час, за 1 день или без уведомления.",
        }
        return SkillResult(
            handled=True,
            answer=(ru if russian else en)[step],
            confidence=1.0,
            action="calendar_create_pending",
            data={"step": step},
        )

    @staticmethod
    def _parse_reminder(text):
        t = str(text).lower().strip()

        # No reminder.
        if any(
            phrase in t
            for phrase in (
                "no notification",
                "no reminder",
                "don't notify me",
                "do not notify me",
                "без уведомления",
                "без напоминания",
                "не уведомляй",
                "не уведомлять",
                "не напоминай",
                "не напоминать",
                "не надо уведомлять",
                "не надо напоминать",
            )
        ) or t in {
            "none",
            "no",
            "нет",
        }:
            return "None"

        # At event time.
        if any(
            phrase in t
            for phrase in (
                "event time",
                "at event",
                "at the event",
                "when event starts",
                "во время события",
                "в момент события",
                "в момент начала",
                "когда событие начнется",
                "когда событие начинается",
                "уведоми во время события",
                "уведоми меня во время события",
                "напомни во время события",
                "напомни мне во время события",
                "уведомить во время события",
            )
        ):
            return "Event Time"

        # 5 minutes before.
        if any(
            phrase in t
            for phrase in (
                "5 minute",
                "five minute",
                "за 5 минут",
                "за пять минут",
                "за 5 мин",
                "пять минут до",
                "5 минут до",
                "напомни за 5 минут",
                "уведоми за 5 минут",
                "уведоми меня за 5 минут",
            )
        ):
            return "5 minutes before"

        # 15 minutes before.
        if any(
            phrase in t
            for phrase in (
                "15 minute",
                "fifteen minute",
                "за 15 минут",
                "за пятнадцать минут",
                "за 15 мин",
                "15 минут до",
                "напомни за 15 минут",
                "уведоми за 15 минут",
                "уведоми меня за 15 минут",
            )
        ):
            return "15 minutes before"

        # 30 minutes before.
        if any(
            phrase in t
            for phrase in (
                "30 minute",
                "thirty minute",
                "за 30 минут",
                "за тридцать минут",
                "за полчаса",
                "за пол часа",
                "30 минут до",
                "напомни за 30 минут",
                "уведоми за 30 минут",
                "уведоми меня за 30 минут",
            )
        ):
            return "30 minutes before"

        # 1 hour before.
        if any(
            phrase in t
            for phrase in (
                "1 hour",
                "one hour",
                "an hour",
                "за час",
                "за 1 час",
                "за один час",
                "за час до",
                "напомни за час",
                "уведоми за час",
                "уведоми меня за час",
            )
        ):
            return "1 hour before"

        # 1 day before.
        if any(
            phrase in t
            for phrase in (
                "1 day",
                "one day",
                "a day",
                "за день",
                "за 1 день",
                "за один день",
                "за сутки",
                "за день до",
                "напомни за день",
                "уведоми за день",
                "уведоми меня за день",
            )
        ):
            return "1 day before"

        return None

    @staticmethod
    def _parse_event_date(text, now):
        if "tomorrow" in text or "завтра" in text:
            return now.date() + timedelta(days=1)
        if "today" in text or "сегодня" in text:
            return now.date()
        weekdays = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
            "понедельник": 0, "вторник": 1, "среда": 2, "среду": 2,
            "четверг": 3, "пятница": 4, "пятницу": 4,
            "суббота": 5, "субботу": 5, "воскресенье": 6,
        }
        for name, weekday in weekdays.items():
            if re.search(rf"\b{re.escape(name)}\b", text):
                delta = (weekday - now.weekday()) % 7
                return now.date() + timedelta(days=(delta or 7))
        return None

    @staticmethod
    def _parse_event_time(text):
        value = str(text).strip().lower()

        m = re.search(
            r"\b(?:at\s+)?"
            r"(\d{1,2})"
            r"(?::(\d{2}))?"
            r"\s*"
            r"([ap])\s*\.?\s*m\.?"
            r"\b",
            value,
            re.IGNORECASE,
        )

        if m:
            hour = int(m.group(1))
            minute = int(m.group(2) or 0)
            meridiem = m.group(3).lower()

            if not (
                1 <= hour <= 12
                and 0 <= minute <= 59
            ):
                return None

            if meridiem == "p" and hour != 12:
                hour += 12
            elif meridiem == "a" and hour == 12:
                hour = 0

            return datetime.strptime(
                f"{hour:02d}:{minute:02d}",
                "%H:%M",
            ).time()

        m = re.search(
            r"\b([01]?\d|2[0-3]):([0-5]\d)\b",
            value,
        )

        if m:
            return datetime.strptime(
                (
                    f"{int(m.group(1)):02d}:"
                    f"{int(m.group(2)):02d}"
                ),
                "%H:%M",
            ).time()

        return None

    def _extract_event_title(
        self,
        original_message,
        normalized,
    ):
        raw = str(
            original_message
        ).strip()

        for prefix in sorted(
            self.CREATE_PREFIXES,
            key=len,
            reverse=True,
        ):
            if not normalized.startswith(
                prefix
            ):
                continue

            words = raw.split()[
                len(prefix.split()):
            ]

            value = " ".join(
                words
            ).strip()

            # Remove optional title introducers.
            value = re.sub(
                r"^(?:called|named|title(?:d)?|"
                r"под названием|с названием)\s+",
                "",
                value,
                flags=re.IGNORECASE,
            )

            # Remove date words.
            value = re.sub(
                r"\b(?:today|tomorrow|"
                r"monday|tuesday|wednesday|thursday|"
                r"friday|saturday|sunday|"
                r"сегодня|завтра)\b",
                " ",
                value,
                flags=re.IGNORECASE,
            )

            # Remove spoken AM/PM times.
            value = re.sub(
                r"\b(?:at\s+)?"
                r"\d{1,2}(?::\d{2})?\s*"
                r"(?:a\.?\s*m\.?|p\.?\s*m\.?)\b",
                " ",
                value,
                flags=re.IGNORECASE,
            )

            # Remove 24-hour times.
            value = re.sub(
                r"\b(?:at\s+)?"
                r"(?:[01]?\d|2[0-3]):[0-5]\d\b",
                " ",
                value,
                flags=re.IGNORECASE,
            )

            # Remove filler/preposition words left after date/time removal.
            value = re.sub(
                r"^(?:for|on|at|for the|on the)\s*",
                "",
                value,
                flags=re.IGNORECASE,
            )

            value = re.sub(
                r"\s+",
                " ",
                value,
            ).strip(
                " ,.-:;"
            )

            # A leftover filler word is not a real event title.
            if self._normalize(
                value
            ) in {
                "",
                "for",
                "on",
                "at",
                "the",
                "for the",
                "on the",
            }:
                return ""

            return value

        return ""

    def _save_created_event(self, title, target_date, target_time, notes, reminder, context, russian):
        event = {
            "title": title,
            "date": target_date.strftime("%Y-%m-%d"),
            "time": target_time.strftime("%H:%M"),
            "notes": notes,
            "reminder": reminder,
            "repeat_mode": "once",
            "days": [],
            "until_date": "",
        }
        events = self._load_events()
        events.append(event)
        try:
            EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            EVENTS_FILE.write_text(json.dumps(events, ensure_ascii=False, indent=4), encoding="utf-8")
            saved = True
        except OSError as error:
            print(f"CalendarSkill save error: {type(error).__name__}: {error}")
            saved = False

        native_alarm = self._schedule_android_event_alarm(event) if saved else False
        when = datetime.combine(target_date, target_time)
        if russian:
            answer = f"Событие «{title}» создано на {when.strftime('%d.%m.%Y %H:%M')}." if saved else "Не удалось сохранить событие."
        else:
            answer = f'Event "{title}" created for {when.strftime("%A, %B %-d at %-I:%M %p")}.' if saved else "I couldn't save the event."

        return SkillResult(
            handled=True,
            answer=answer,
            confidence=1.0,
            action="calendar_event_created" if saved else "calendar_event_save_error",
            data={"saved": saved, "event": event, "native_alarm_scheduled": native_alarm},
        )

    @staticmethod
    def _schedule_android_event_alarm(event):
        if platform != "android":
            return False

        if not callable(schedule_android_event):
            print("[CalendarSkill] Android event scheduler unavailable.")
            return False

        try:
            return bool(schedule_android_event(event))
        except Exception as error:
            print(
                "[CalendarSkill] Android event alarm error: "
                f"{type(error).__name__}: {error}"
            )
            return False

    @staticmethod
    def _normalize(message: str) -> str:
        text = str(message).strip().lower()
        text = text.replace("’", "'")
        text = re.sub(
            r"[^a-z0-9а-яё'\s-]+",
            " ",
            text,
        )
        return " ".join(text.split())

    @staticmethod
    def _is_russian(text: str) -> bool:
        return bool(
            re.search(
                r"[а-яё]",
                text,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _open_calendar(context: Any) -> bool:
        if context is None:
            return False

        method = getattr(
            context,
            "open_screen",
            None,
        )

        if callable(method):
            try:
                return bool(method("calendar"))
            except Exception as error:
                print(
                    "CalendarSkill open error: "
                    f"{type(error).__name__}: {error}"
                )

        if isinstance(context, dict):
            callback = context.get("open_screen")

            if callable(callback):
                try:
                    return bool(callback("calendar"))
                except Exception as error:
                    print(
                        "CalendarSkill open callback error: "
                        f"{type(error).__name__}: {error}"
                    )

        return False

    @staticmethod
    def _load_events() -> list[dict]:
        if not EVENTS_FILE.exists():
            return []

        try:
            loaded = json.loads(
                EVENTS_FILE.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            print(
                "CalendarSkill load error: "
                f"{type(error).__name__}: {error}"
            )
            return []

        if not isinstance(loaded, list):
            return []

        return [
            event
            for event in loaded
            if isinstance(event, dict)
        ]

    @staticmethod
    def _base_datetime(
        event: dict,
    ) -> datetime | None:
        date_text = str(
            event.get("date", "")
        ).strip()

        time_text = str(
            event.get("time", "")
        ).strip() or "00:00"

        try:
            return datetime.strptime(
                f"{date_text} {time_text}",
                "%Y-%m-%d %H:%M",
            )
        except ValueError:
            return None

    @staticmethod
    def _until_date(
        event: dict,
    ) -> date | None:
        value = str(
            event.get("until_date", "")
        ).strip()

        if not value:
            return None

        try:
            return datetime.strptime(
                value,
                "%Y-%m-%d",
            ).date()
        except ValueError:
            return None

    def _occurrence_on_date(
        self,
        event: dict,
        target_date: date,
    ) -> datetime | None:
        base = self._base_datetime(event)

        if base is None:
            return None

        mode = str(
            event.get(
                "repeat_mode",
                "once",
            )
        ).strip()

        if mode == "once":
            if base.date() != target_date:
                return None
            return base

        if target_date < base.date():
            return None

        until = self._until_date(event)

        if until is not None and target_date > until:
            return None

        if mode == "every_day":
            return datetime.combine(
                target_date,
                base.time(),
            )

        if mode == "days":
            days = event.get("days", [])

            if not isinstance(days, list):
                return None

            day_name = DAY_NAMES[
                target_date.weekday()
            ]

            if day_name not in days:
                return None

            return datetime.combine(
                target_date,
                base.time(),
            )

        return None

    def _occurrences_between(
        self,
        events: list[dict],
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[tuple[datetime, dict]]:
        results = []

        current_date = start.date()
        final_date = end.date()

        while current_date <= final_date:
            for event in events:
                occurrence = self._occurrence_on_date(
                    event,
                    current_date,
                )

                if occurrence is None:
                    continue

                if start <= occurrence < end:
                    results.append(
                        (
                            occurrence,
                            event,
                        )
                    )

            current_date += timedelta(days=1)

        results.sort(
            key=lambda item: item[0]
        )

        return results[:max(1, int(limit))]

    def _build_result(
        self,
        occurrences: list[tuple[datetime, dict]],
        period: str,
        russian: bool,
        confidence: float,
    ) -> SkillResult:
        if not occurrences:
            answer = self._no_events_answer(
                period=period,
                russian=russian,
            )

            return SkillResult(
                handled=True,
                answer=answer,
                confidence=confidence,
                action="calendar_events",
                data={
                    "period": period,
                    "count": 0,
                    "events": [],
                },
            )

        lines = []

        for occurrence, event in occurrences:
            title = str(
                event.get(
                    "title",
                    "Untitled Event",
                )
            ).strip() or "Untitled Event"

            notes = str(
                event.get(
                    "notes",
                    "",
                )
            ).strip()

            if period == "today":
                when = occurrence.strftime(
                    "%-I:%M %p"
                )
            elif period == "tomorrow":
                when = occurrence.strftime(
                    "%-I:%M %p"
                )
            else:
                when = occurrence.strftime(
                    "%A, %B %-d at %-I:%M %p"
                )

            line = f"{when}: {title}"

            if notes:
                line += f" — {notes}"

            lines.append(line)

        if period == "next":
            prefix = (
                "Ваше следующее событие:"
                if russian
                else "Your next event is:"
            )
        elif period == "tomorrow":
            prefix = (
                "События на завтра:"
                if russian
                else "Your events tomorrow:"
            )
        elif period == "week":
            prefix = (
                "События на ближайшие 7 дней:"
                if russian
                else "Your events for the next 7 days:"
            )
        else:
            prefix = (
                "Ваши события сегодня:"
                if russian
                else "Your events today:"
            )

        answer = prefix + "\n" + "\n".join(
            f"{index}. {line}"
            for index, line in enumerate(
                lines,
                start=1,
            )
        )

        data_events = [
            {
                "title": str(
                    event.get(
                        "title",
                        "Untitled Event",
                    )
                ).strip(),
                "datetime": occurrence.isoformat(),
                "notes": str(
                    event.get(
                        "notes",
                        "",
                    )
                ).strip(),
                "repeat_mode": str(
                    event.get(
                        "repeat_mode",
                        "once",
                    )
                ),
            }
            for occurrence, event in occurrences
        ]

        return SkillResult(
            handled=True,
            answer=answer,
            confidence=confidence,
            action="calendar_events",
            data={
                "period": period,
                "count": len(data_events),
                "events": data_events,
            },
        )

    @staticmethod
    def _no_events_answer(
        period: str,
        russian: bool,
    ) -> str:
        if russian:
            answers = {
                "next": "У вас нет предстоящих событий.",
                "tomorrow": "На завтра у вас нет событий.",
                "week": "На ближайшие 7 дней у вас нет событий.",
                "today": "На сегодня у вас больше нет событий.",
            }
        else:
            answers = {
                "next": "You have no upcoming events.",
                "tomorrow": "You have no events tomorrow.",
                "week": "You have no events in the next 7 days.",
                "today": "You have no more events today.",
            }

        return answers.get(
            period,
            answers["today"],
        )