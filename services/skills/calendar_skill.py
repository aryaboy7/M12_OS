import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from services.skills.base_skill import BaseSkill, SkillResult


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
