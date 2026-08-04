from datetime import datetime
from typing import Any

from services.skills.base_skill import BaseSkill, SkillResult


class TimeSkill(BaseSkill):
    """Handle local date and time questions."""

    name = "time"
    priority = 30

    TIME_PHRASES = {
        "what time is it",
        "what is the time",
        "what is the current time",
        "current time",
        "tell me the time",
        "time now",
    }

    DATE_PHRASES = {
        "what day is today",
        "what day is it",
        "what is todays date",
        "what is today's date",
        "what is the date",
        "current date",
        "date today",
    }

    RUSSIAN_TIME_PHRASES = {
        "который час",
        "сколько времени",
        "какое сейчас время",
        "сколько сейчас времени",
    }

    RUSSIAN_DATE_PHRASES = {
        "какой сегодня день",
        "какая сегодня дата",
        "какое сегодня число",
    }

    def can_handle(self, message: str, context: Any) -> float:
        text = self._normalize(message)
        print(
            f"[TimeSkill] can_handle original={message!r} "
            f"normalized={text!r}"
        )

        if text in self.TIME_PHRASES:
            return 0.98

        if text in self.DATE_PHRASES:
            return 0.98

        if text in self.RUSSIAN_TIME_PHRASES:
            return 0.98

        if text in self.RUSSIAN_DATE_PHRASES:
            return 0.98

        return 0.0

    def handle(self, message: str, context: Any) -> SkillResult:
        text = self._normalize(message)
        now = datetime.now()

        print(
            f"[TimeSkill] handle normalized={text!r} "
            f"now={now.isoformat(timespec='seconds')}"
        )

        if text in self.TIME_PHRASES:
            return SkillResult(
                handled=True,
                answer=(
                    "The current time is "
                    f"{now.strftime('%I:%M %p').lstrip('0')}."
                ),
                confidence=0.98,
                action="show_time",
                data={
                    "hour": now.hour,
                    "minute": now.minute,
                    "second": now.second,
                },
            )

        if text in self.DATE_PHRASES:
            return SkillResult(
                handled=True,
                answer=(
                    f"Today is {now.strftime('%A, %B')} "
                    f"{now.day}, {now.year}."
                ),
                confidence=0.98,
                action="show_date",
                data={
                    "year": now.year,
                    "month": now.month,
                    "day": now.day,
                    "weekday": now.strftime("%A"),
                },
            )

        if text in self.RUSSIAN_TIME_PHRASES:
            return SkillResult(
                handled=True,
                answer=f"Сейчас {now.hour:02d}:{now.minute:02d}.",
                confidence=0.98,
                action="show_time",
                data={
                    "hour": now.hour,
                    "minute": now.minute,
                    "second": now.second,
                },
            )

        if text in self.RUSSIAN_DATE_PHRASES:
            return SkillResult(
                handled=True,
                answer=(
                    f"Сегодня {now.day:02d}."
                    f"{now.month:02d}.{now.year}."
                ),
                confidence=0.98,
                action="show_date",
                data={
                    "year": now.year,
                    "month": now.month,
                    "day": now.day,
                    "weekday": now.strftime("%A"),
                },
            )

        return SkillResult(handled=False)

    @staticmethod
    def _normalize(message: str) -> str:
        text = str(message).strip().lower()
        text = text.replace("’", "'")
        text = text.rstrip("?!.,")
        return " ".join(text.split())
