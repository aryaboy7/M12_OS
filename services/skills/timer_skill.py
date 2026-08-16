import json
import re
from typing import Any

from services.skills.activity_context import ActivityContext
from services.skills.base_skill import BaseSkill, SkillResult


class TimerSkill(BaseSkill):
    """
    Voice control for the existing M12OS TimerScreen.

    This skill uses TimerScreen as the only timer engine.
    It does not maintain a second countdown.
    """

    name = "timer"
    priority = 2

    STRUCTURED_PREFIX = "__M12_TIMER__:"

    OPEN = {
        "open timer",
        "show timer",
        "can i see timer",
        "timer",
        "открой таймер",
        "покажи таймер",
        "таймер",
    }

    PAUSE = {
        "pause timer",
        "pause the timer",
        "поставь таймер на паузу",
        "приостанови таймер",
    }

    RESUME = {
        "resume timer",
        "resume the timer",
        "continue timer",
        "continue the timer",
        "продолжи таймер",
        "возобнови таймер",
    }

    STOP = {
        "stop timer",
        "stop the timer",
        "cancel timer",
        "останови таймер",
        "отмени таймер",
    }

    RESET = {
        "reset timer",
        "reset the timer",
        "clear timer",
        "сбрось таймер",
        "обнули таймер",
    }

    STATUS = {
        "how much time is left",
        "how much time left",
        "what time is left",
        "what time left",
        "how much is left",
        "time left",
        "remaining",
        "timer status",
        "how long",
        "сколько осталось",
        "сколько времени осталось",
        "сколько ещё",
    }

    ACTIVE_PAUSE = {
        "pause",
        "pause it",
        "hold it",
        "пауза",
        "приостанови",
        "поставь на паузу",
    }

    ACTIVE_RESUME = {
        "resume",
        "resume it",
        "continue",
        "continue it",
        "продолжи",
        "возобнови",
    }

    ACTIVE_STOP = {
        "stop it",
        "stopit",
        "tap it",
        "tapit",
        "top it",
        "cancel it",
        "останови",
        "отмени",
    }

    ACTIVE_RESET = {
        "reset it",
        "clear it",
        "сбрось",
        "обнули",
    }

    START_PREFIXES = (
        "set timer",
        "set a timer",
        "start timer",
        "start a timer",
        "timer for",
        "timer to",
        "поставь таймер",
        "установи таймер",
        "запусти таймер",
    )

    NUMBER_WORDS = {
        "zero": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,

        "ноль": 0,
        "одну": 1,
        "один": 1,
        "одна": 1,
        "два": 2,
        "две": 2,
        "три": 3,
        "четыре": 4,
        "пять": 5,
        "шесть": 6,
        "семь": 7,
        "восемь": 8,
        "девять": 9,
        "десять": 10,
    }

    def can_handle(
        self,
        message: str,
        context: Any,
    ) -> float:
        raw = str(message).strip()

        if raw.startswith(self.STRUCTURED_PREFIX):
            return 1.0

        text = self._normalize(message)

        if not text:
            return 0.0

        activity = ActivityContext.instance().current()

        if activity == "timer":
            if (
                text in self.ACTIVE_PAUSE
                or text in self.ACTIVE_RESUME
                or text in self.ACTIVE_STOP
                or text in self.ACTIVE_RESET
                or text in self.STATUS
            ):
                return 1.0

        if (
            text in self.OPEN
            or text in self.PAUSE
            or text in self.RESUME
            or text in self.STOP
            or text in self.RESET
            or text in self.STATUS
        ):
            return 1.0

        if text.startswith(self.START_PREFIXES):
            return 1.0

        if "timer" in text or "таймер" in text:
            return 0.99

        return 0.0

    def handle(
        self,
        message: str,
        context: Any,
    ) -> SkillResult:
        raw = str(message).strip()

        if raw.startswith(self.STRUCTURED_PREFIX):
            return self._handle_structured(
                raw=raw,
                context=context,
            )

        text = self._normalize(message)
        russian = self._is_russian(text)

        if text in self.OPEN:
            opened, _ = self._get_screen(
                context=context,
                open_screen=True,
            )

            return self._simple_result(
                success=opened,
                success_answer=(
                    "Таймер открыт."
                    if russian
                    else "Timer opened."
                ),
                failure_answer=(
                    "Не удалось открыть таймер."
                    if russian
                    else "I couldn't open the timer."
                ),
                action="open_timer",
            )

        available, screen = self._get_screen(
            context=context,
            open_screen=False,
        )

        if not available:
            return SkillResult(
                handled=True,
                answer=(
                    "Экран таймера недоступен."
                    if russian
                    else "The Timer screen is unavailable."
                ),
                confidence=1.0,
                action="timer_error",
            )

        if text in self.PAUSE or text in self.ACTIVE_PAUSE:
            screen.stop(None)
            ActivityContext.instance().set("timer")

            return SkillResult(
                handled=True,
                answer=(
                    "Таймер поставлен на паузу."
                    if russian
                    else "Timer paused."
                ),
                confidence=1.0,
                action="pause_timer",
                data={
                    "remaining_seconds": int(screen.remaining),
                    "running": bool(screen.running),
                },
            )

        if text in self.RESUME or text in self.ACTIVE_RESUME:
            if int(screen.remaining) <= 0:
                answer = (
                    "Таймер не установлен."
                    if russian
                    else "No timer is set."
                )

                return SkillResult(
                    handled=True,
                    answer=answer,
                    confidence=1.0,
                    action="resume_timer",
                    data={"resumed": False},
                )

            screen.start(None)
            ActivityContext.instance().set("timer")

            return SkillResult(
                handled=True,
                answer=(
                    "Таймер продолжен."
                    if russian
                    else "Timer resumed."
                ),
                confidence=1.0,
                action="resume_timer",
                data={
                    "remaining_seconds": int(screen.remaining),
                    "running": bool(screen.running),
                },
            )

        if text in self.STOP or text in self.ACTIVE_STOP:
            screen.stop(None)
            ActivityContext.instance().set("timer")

            return SkillResult(
                handled=True,
                answer=(
                    "Таймер остановлен."
                    if russian
                    else "Timer stopped."
                ),
                confidence=1.0,
                action="stop_timer",
                data={
                    "remaining_seconds": int(screen.remaining),
                    "running": bool(screen.running),
                },
            )

        if text in self.RESET or text in self.ACTIVE_RESET:
            screen.reset(None)
            ActivityContext.instance().clear()

            return SkillResult(
                handled=True,
                answer=(
                    "Таймер сброшен."
                    if russian
                    else "Timer reset."
                ),
                confidence=1.0,
                action="reset_timer",
                data={
                    "remaining_seconds": int(screen.remaining),
                    "running": bool(screen.running),
                },
            )

        if text in self.STATUS:
            remaining = int(screen.remaining)

            if (
                remaining <= 0
                and not screen.running
            ):
                return SkillResult(
                    handled=True,
                    answer=(
                        "Таймер не запущен."
                        if russian
                        else "The timer is not running."
                    ),
                    confidence=1.0,
                    action="timer_status",
                    data={
                        "remaining_seconds": 0,
                        "running": False,
                    },
                )

            formatted = self._format_duration(
                seconds=remaining,
                russian=russian,
            )

            return SkillResult(
                handled=True,
                answer=(
                    f"Осталось {formatted}."
                    if russian
                    else f"{formatted} remaining."
                ),
                confidence=1.0,
                action="timer_status",
                data={
                    "remaining_seconds": remaining,
                    "running": bool(screen.running),
                },
            )

        duration = self._parse_duration(text)

        if duration is None or duration <= 0:
            return SkillResult(
                handled=True,
                answer=(
                    "Скажите длительность таймера. "
                    "Например: семь минут."
                    if russian
                    else
                    "Tell me the timer duration. "
                    "For example: seven minutes."
                ),
                confidence=1.0,
                action="timer_needs_duration",
            )

        started = self._set_timer(
            screen=screen,
            total_seconds=duration,
        )

        if started:
            ActivityContext.instance().set("timer")

        formatted = self._format_duration(
            seconds=duration,
            russian=russian,
        )

        return SkillResult(
            handled=True,
            answer=(
                f"Таймер запущен на {formatted}."
                if russian and started
                else "Не удалось запустить таймер."
                if russian
                else f"Timer started for {formatted}."
                if started
                else "I couldn't start the timer."
            ),
            confidence=1.0,
            action="start_timer",
            data={
                "seconds": duration,
                "started": started,
                "screen_remaining": int(
                    getattr(
                        screen,
                        "remaining",
                        0,
                    )
                ),
            },
        )

    @classmethod
    def _handle_structured(
        cls,
        raw: str,
        context: Any,
    ) -> SkillResult:
        """Execute a language-independent command produced by Realtime."""
        payload_text = raw[len(cls.STRUCTURED_PREFIX):].strip()

        try:
            payload = json.loads(payload_text)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            print(
                "TimerSkill structured JSON error: "
                f"{type(error).__name__}: {error}"
            )
            return SkillResult(
                handled=True,
                answer="",
                confidence=1.0,
                action="timer_error",
                data={"success": False, "error": "invalid_json"},
            )

        action = str(payload.get("action", "")).strip().lower()

        try:
            seconds = int(payload.get("seconds", 0))
        except (TypeError, ValueError):
            seconds = 0

        available, screen = cls._get_screen(
            context=context,
            open_screen=False,
        )

        if not available:
            return SkillResult(
                handled=True,
                answer="",
                confidence=1.0,
                action="timer_error",
                data={"success": False, "error": "screen_unavailable"},
            )

        if action == "pause":
            if not bool(getattr(screen, "running", False)):
                return SkillResult(
                    handled=True,
                    answer="",
                    confidence=1.0,
                    action="pause_timer",
                    data={
                        "success": False,
                        "paused": False,
                        "error": "timer_not_running",
                        "remaining_seconds": int(
                            getattr(screen, "remaining", 0)
                        ),
                    },
                )

            screen.stop(None)
            ActivityContext.instance().set("timer")

            return SkillResult(
                handled=True,
                answer="",
                confidence=1.0,
                action="pause_timer",
                data={
                    "success": True,
                    "paused": True,
                    "remaining_seconds": int(
                        getattr(screen, "remaining", 0)
                    ),
                },
            )

        if action == "resume":
            remaining = int(getattr(screen, "remaining", 0))

            if remaining <= 0:
                return SkillResult(
                    handled=True,
                    answer="",
                    confidence=1.0,
                    action="resume_timer",
                    data={
                        "success": False,
                        "resumed": False,
                        "error": "timer_not_set",
                        "remaining_seconds": 0,
                    },
                )

            screen.start(None)
            resumed = bool(getattr(screen, "running", False))

            if resumed:
                ActivityContext.instance().set("timer")

            return SkillResult(
                handled=True,
                answer="",
                confidence=1.0,
                action="resume_timer",
                data={
                    "success": resumed,
                    "resumed": resumed,
                    "remaining_seconds": int(
                        getattr(screen, "remaining", 0)
                    ),
                },
            )

        if action != "start":
            return SkillResult(
                handled=True,
                answer="",
                confidence=1.0,
                action="timer_error",
                data={"success": False, "error": "unsupported_action"},
            )

        if seconds <= 0 or seconds > 86399:
            return SkillResult(
                handled=True,
                answer="",
                confidence=1.0,
                action="timer_error",
                data={"success": False, "error": "invalid_duration"},
            )

        started = cls._set_timer(
            screen=screen,
            total_seconds=seconds,
        )

        if started:
            ActivityContext.instance().set("timer")

        return SkillResult(
            handled=True,
            answer="",
            confidence=1.0,
            action="start_timer",
            data={
                "success": bool(started),
                "started": bool(started),
                "seconds": seconds,
                "remaining_seconds": int(
                    getattr(screen, "remaining", 0)
                ),
            },
        )

    @staticmethod
    def _normalize(message: str) -> str:
        text = str(message).strip().lower()
        text = text.replace("’", "'")
        text = re.sub(
            r"[!?;,]+",
            " ",
            text,
        )
        text = re.sub(
            r"\.(?=\s*$)",
            "",
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

    @classmethod
    def _parse_duration(
        cls,
        text: str,
    ) -> int | None:
        value = text

        phrase_replacements = (
            (
                r"\bone and a half hours?\b",
                "1.5 hours",
            ),
            (
                r"\bone and a half minutes?\b",
                "1.5 minutes",
            ),
            (
                r"\bhalf an hour\b",
                "30 minutes",
            ),
            (
                r"\bhalf hour\b",
                "30 minutes",
            ),
            (
                r"\bhalf a minute\b",
                "30 seconds",
            ),
            (
                r"\bquarter of an hour\b",
                "15 minutes",
            ),
            (
                r"\bquarter hour\b",
                "15 minutes",
            ),
            (
                r"\bполтора часа\b",
                "1.5 часа",
            ),
            (
                r"\bполторы минуты\b",
                "1.5 минуты",
            ),
            (
                r"\bполминуты\b",
                "30 секунд",
            ),
            (
                r"\bполчаса\b",
                "30 минут",
            ),
            (
                r"\bчетверть часа\b",
                "15 минут",
            ),
        )

        for pattern, replacement in phrase_replacements:
            value = re.sub(
                pattern,
                replacement,
                value,
                flags=re.IGNORECASE,
            )

        for word, number in cls.NUMBER_WORDS.items():
            value = re.sub(
                rf"\b{re.escape(word)}\b",
                str(number),
                value,
                flags=re.IGNORECASE,
            )

        total = 0
        found = False

        patterns = (
            (
                r"(\d+(?:\.\d+)?)\s*"
                r"(?:hours?|hrs?|час(?:а|ов)?)\b",
                3600,
            ),
            (
                r"(\d+(?:\.\d+)?)\s*"
                r"(?:minutes?|mins?|минут(?:а|ы)?)\b",
                60,
            ),
            (
                r"(\d+(?:\.\d+)?)\s*"
                r"(?:seconds?|secs?|секунд(?:а|ы)?)\b",
                1,
            ),
        )

        for pattern, multiplier in patterns:
            for match in re.finditer(
                pattern,
                value,
                re.IGNORECASE,
            ):
                total += int(
                    round(
                        float(match.group(1))
                        * multiplier
                    )
                )
                found = True

        if found:
            return total

        match = re.search(
            r"\b(\d+)\b",
            value,
        )

        if (
            match
            and (
                "timer" in value
                or "таймер" in value
            )
        ):
            return int(match.group(1)) * 60

        return None

    @staticmethod
    def _get_screen(
        context: Any,
        open_screen: bool,
    ) -> tuple[bool, Any]:
        if context is None:
            return False, None

        if open_screen:
            opener = getattr(
                context,
                "open_screen",
                None,
            )

            if (
                not callable(opener)
                or not opener("timer")
            ):
                return False, None

        getter = getattr(
            context,
            "get_screen",
            None,
        )

        if not callable(getter):
            return False, None

        try:
            screen = getter("timer")
        except Exception as error:
            print(
                "TimerSkill get_screen error: "
                f"{type(error).__name__}: {error}"
            )
            return False, None

        required = (
            "hours_wheel",
            "minutes_wheel",
            "seconds_wheel",
            "remaining",
            "original_seconds",
            "running",
            "start",
            "stop",
            "reset",
            "update_display",
        )

        if not all(
            hasattr(screen, name)
            for name in required
        ):
            print(
                "TimerSkill: TimerScreen API does not "
                "match the expected M12OS interface."
            )
            return False, None

        return True, screen

    @staticmethod
    def _set_timer(
        screen: Any,
        total_seconds: int,
    ) -> bool:
        total = max(
            1,
            int(total_seconds),
        )

        hours, remainder = divmod(
            total,
            3600,
        )
        minutes, seconds = divmod(
            remainder,
            60,
        )

        if hours > 23:
            return False

        try:
            # Stop the previous timer without changing its duration.
            screen.stop(None)

            # Set the visible wheels.
            screen.hours_wheel.value = hours
            screen.minutes_wheel.value = minutes
            screen.seconds_wheel.value = seconds

            screen.hours_wheel.update_labels()
            screen.minutes_wheel.update_labels()
            screen.seconds_wheel.update_labels()

            # Replace the previous countdown completely.
            screen.remaining = total
            screen.original_seconds = total
            screen.running = False

            screen.update_display()
            screen.start(None)

            return (
                bool(screen.running)
                and int(screen.remaining) == total
            )

        except Exception as error:
            print(
                "TimerSkill start error: "
                f"{type(error).__name__}: {error}"
            )
            return False

    @staticmethod
    def _format_duration(
        seconds: int,
        russian: bool,
    ) -> str:
        total = max(
            0,
            int(seconds),
        )

        hours, remainder = divmod(
            total,
            3600,
        )
        minutes, secs = divmod(
            remainder,
            60,
        )

        parts = []

        if hours:
            parts.append(
                f"{hours} "
                + (
                    "час."
                    if russian
                    else (
                        "hour"
                        if hours == 1
                        else "hours"
                    )
                )
            )

        if minutes:
            parts.append(
                f"{minutes} "
                + (
                    "мин."
                    if russian
                    else (
                        "minute"
                        if minutes == 1
                        else "minutes"
                    )
                )
            )

        if secs or not parts:
            parts.append(
                f"{secs} "
                + (
                    "сек."
                    if russian
                    else (
                        "second"
                        if secs == 1
                        else "seconds"
                    )
                )
            )

        return " ".join(parts)

    @staticmethod
    def _simple_result(
        success: bool,
        success_answer: str,
        failure_answer: str,
        action: str,
    ) -> SkillResult:
        return SkillResult(
            handled=True,
            answer=(
                success_answer
                if success
                else failure_answer
            ),
            confidence=1.0,
            action=action,
            data={"success": success},
        )
