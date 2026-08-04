import re
from typing import Any

from services.skills.base_skill import BaseSkill, SkillResult
from services.skills.activity_context import ActivityContext


class StopwatchSkill(BaseSkill):
    """Voice control for the existing M12OS Stopwatch screen."""

    name = "stopwatch"
    priority = 2

    OPEN = {
        "open stopwatch",
        "show stopwatch",
        "can i see stopwatch",
        "let me see stopwatch",
        "stopwatch",
        "открой секундомер",
        "покажи секундомер",
        "можно посмотреть секундомер",
        "секундомер",
    }
    START = {
        "start stopwatch",
        "start the stopwatch",
        "start stop watch",
        "start stop-watch",
        "старт секундомера",
        "старт секундомер",
        "запусти секундомер",
        "запустить секундомер",
        "старт стопоч",
        "старт стопвоч",
        "старт стопвач",
        "старт стоп вотч",
        "старт стоп",
    }
    STOP = {
        "stop stopwatch", "stop the stopwatch", "pause stopwatch",
        "останови секундомер", "поставь секундомер на паузу",
    }
    RESUME = {
        "resume stopwatch", "continue stopwatch",
        "продолжи секундомер", "возобнови секундомер",
    }
    RESET = {
        "reset stopwatch", "clear stopwatch",
        "сбрось секундомер", "обнули секундомер",
    }
    STATUS = {
        "stopwatch time",
        "what is the stopwatch time",
        "what time is it now in stopwatch",
        "what time is it in stopwatch",
        "what time is on stopwatch",
        "what time on stopwatch",
        "how much time is on stopwatch",
        "how long",
        "сколько на секундомере",
        "сколько времени на секундомере",
        "какое время на секундомере",
        "время секундомера",
    }

    ACTIVE_START = {
        "start it",
        "resume",
        "resume it",
        "continue",
        "continue it",
        "запусти",
        "продолжи",
        "возобнови",
    }

    ACTIVE_STOP = {
        "stop it",
        "pause it",
        "останови",
        "пауза",
    }

    ACTIVE_RESET = {
        "reset it",
        "clear it",
        "сбрось",
        "обнули",
    }

    @classmethod
    def _is_status_command(
        cls,
        text: str,
    ) -> bool:
        if text in cls.STATUS:
            return True

        has_stopwatch = cls._has_stopwatch_reference(
            text
        )

        if not has_stopwatch:
            return False

        english_status = (
            "time" in text
            and any(
                word in text
                for word in (
                    "what",
                    "how much",
                    "show",
                    "tell",
                )
            )
        )

        russian_status = (
            "секундомер" in text
            and any(
                word in text
                for word in (
                    "сколько",
                    "время",
                    "какое",
                    "покажи",
                )
            )
        )

        return english_status or russian_status

    def can_handle(
        self,
        message: str,
        context: Any,
    ) -> float:
        text = self._normalize(message)

        if not text:
            return 0.0

        activity = ActivityContext.instance().current()

        if activity == "stopwatch":
            if (
                text in self.ACTIVE_START
                or text in self.ACTIVE_STOP
                or text in self.ACTIVE_RESET
                or self._is_status_command(text)
            ):
                return 1.0

        if (
            text in self.OPEN
            or self._is_start_command(text)
            or self._is_stop_command(text)
            or text in self.RESUME
            or text in self.RESET
            or self._is_status_command(text)
        ):
            return 1.0

        if self._has_stopwatch_reference(text):
            return 1.0

        return 0.0

    def handle(self, message: str, context: Any) -> SkillResult:
        text = self._normalize(message)
        russian = self._is_russian(text)

        if text in self.OPEN:
            ok, _ = self._screen(context, open_it=True)
            return self._result(
                ok,
                "Секундомер открыт." if russian else "Stopwatch opened.",
                "Не удалось открыть секундомер." if russian else "I couldn't open the stopwatch.",
                "open_stopwatch",
            )

        ok, screen = self._screen(context, open_it=False)
        if not ok:
            return self._result(
                False,
                "",
                "Экран секундомера недоступен." if russian else "The Stopwatch screen is unavailable.",
                "stopwatch_error",
            )

        if self._is_start_command(text) or text in self.ACTIVE_START:
            success = self._start(screen)

            if success:
                ActivityContext.instance().set("stopwatch")

            return self._result(
                success,
                "Секундомер запущен." if russian else "Stopwatch started.",
                "Не удалось запустить секундомер." if russian else "I couldn't start the stopwatch.",
                "start_stopwatch",
            )

        if self._is_stop_command(text) or text in self.ACTIVE_STOP:
            success = self._stop(screen)

            if success:
                ActivityContext.instance().set("stopwatch")

            return self._result(
                success,
                "Секундомер остановлен." if russian else "Stopwatch stopped.",
                "Не удалось остановить секундомер." if russian else "I couldn't stop the stopwatch.",
                "stop_stopwatch",
            )

        if text in self.RESUME:
            success = self._start(screen)

            if success:
                ActivityContext.instance().set("stopwatch")

            return self._result(
                success,
                "Секундомер продолжен." if russian else "Stopwatch resumed.",
                "Не удалось продолжить секундомер." if russian else "I couldn't resume the stopwatch.",
                "resume_stopwatch",
            )

        if text in self.RESET or text in self.ACTIVE_RESET:
            success = self._call_first(
                screen,
                ("reset_stopwatch", "reset", "clear_stopwatch", "clear"),
            )

            if success:
                ActivityContext.instance().clear()

            return self._result(
                success,
                "Секундомер сброшен." if russian else "Stopwatch reset.",
                "Не удалось сбросить секундомер." if russian else "I couldn't reset the stopwatch.",
                "reset_stopwatch",
            )

        if self._is_status_command(text):
            elapsed = self._elapsed_seconds(screen)
            if elapsed is None:
                answer = (
                    "Не удалось определить время секундомера."
                    if russian
                    else "I couldn't determine the stopwatch time."
                )
                return SkillResult(True, answer, 1.0, "stopwatch_status")

            answer = (
                f"На секундомере {self._format_elapsed(elapsed)}."
                if russian
                else f"The stopwatch shows {self._format_elapsed(elapsed)}."
            )
            return SkillResult(
                True,
                answer,
                1.0,
                "stopwatch_status",
                {"elapsed_seconds": elapsed},
            )

        return SkillResult(handled=False)

    @staticmethod
    def _has_stopwatch_reference(
        text: str,
    ) -> bool:
        compact = re.sub(
            r"[^a-zа-яё]+",
            "",
            text,
            flags=re.IGNORECASE,
        )

        return bool(
            "stopwatch" in compact
            or "stopvotch" in compact
            or "секундомер" in compact
            or "стопоч" in compact
            or "стоппоч" in compact
            or "стопвоч" in compact
            or "стопвач" in compact
            or "стоппочь" in compact
        )

    @classmethod
    def _is_start_command(
        cls,
        text: str,
    ) -> bool:
        if text in cls.START:
            return True

        words = set(text.split())

        has_start = bool(
            words.intersection(
                {
                    "start",
                    "старт",
                    "запусти",
                    "запустить",
                    "начни",
                }
            )
        )

        # Speech can split "stopwatch" into "stop watch"
        # or Russian phonetic pieces such as "стоп поч".
        compact = re.sub(
            r"[^a-zа-яё]+",
            "",
            text,
            flags=re.IGNORECASE,
        )

        has_stopwatch = bool(
            cls._has_stopwatch_reference(text)
            or (
                "stop" in words
                and "watch" in words
            )
            or (
                "стоп" in words
                and bool(
                    words.intersection(
                        {
                            "поч",
                            "почь",
                            "воч",
                            "вач",
                            "вотч",
                        }
                    )
                )
            )
            or "стартстоп" in compact
        )

        return has_start and has_stopwatch

    @classmethod
    def _is_stop_command(
        cls,
        text: str,
    ) -> bool:
        if text in cls.STOP:
            return True

        words = set(text.split())

        has_stop = bool(
            words.intersection(
                {
                    "stop",
                    "pause",
                    "останови",
                    "остановить",
                    "пауза",
                }
            )
        )

        return (
            has_stop
            and cls._has_stopwatch_reference(text)
        )

    @staticmethod
    def _normalize(message: str) -> str:
        text = str(message).strip().lower().replace("’", "'")

        # Normalize punctuation and mixed speech-to-text output.
        text = text.replace("-", " ")
        text = text.replace("–", " ")
        text = text.replace("—", " ")
        text = re.sub(r"[!?;,]+", " ", text)
        text = re.sub(r"\.(?=\s*$)", "", text)

        # Remove uncommon combining/Latin endings that can appear
        # in mixed Russian-English transcriptions such as
        # "Старт-стопoč".
        text = text.replace("oč", "оч")
        text = text.replace("č", "ч")
        text = text.replace("ć", "ч")
        text = text.replace("š", "ш")
        text = text.replace("ž", "ж")

        return " ".join(text.split())

    @staticmethod
    def _is_russian(text: str) -> bool:
        return bool(re.search(r"[а-яё]", text, re.I))

    @staticmethod
    def _screen(context: Any, open_it: bool) -> tuple[bool, Any]:
        if context is None:
            return False, None

        if open_it:
            opener = getattr(context, "open_screen", None)
            if not callable(opener) or not opener("stopwatch"):
                return False, None

        getter = getattr(context, "get_screen", None)
        if not callable(getter):
            return False, None

        try:
            return True, getter("stopwatch")
        except Exception:
            return False, None

    @classmethod
    def _start(cls, screen: Any) -> bool:
        if cls._call_first(
            screen,
            ("start_stopwatch", "start", "resume_stopwatch", "resume"),
        ):
            return True

        # Many stopwatch screens use one toggle method.
        running = bool(
            getattr(screen, "running", getattr(screen, "is_running", False))
        )
        if not running and cls._call_first(
            screen,
            ("start_stop", "toggle_stopwatch", "toggle"),
        ):
            return True

        for attr in ("running", "is_running"):
            if hasattr(screen, attr):
                try:
                    setattr(screen, attr, True)
                    return True
                except Exception:
                    pass
        return False

    @classmethod
    def _stop(cls, screen: Any) -> bool:
        if cls._call_first(
            screen,
            ("stop_stopwatch", "stop", "pause_stopwatch", "pause"),
        ):
            return True

        running = bool(
            getattr(screen, "running", getattr(screen, "is_running", False))
        )
        if running and cls._call_first(
            screen,
            ("start_stop", "toggle_stopwatch", "toggle"),
        ):
            return True

        for attr in ("running", "is_running"):
            if hasattr(screen, attr):
                try:
                    setattr(screen, attr, False)
                    return True
                except Exception:
                    pass
        return False

    @staticmethod
    def _call_first(screen: Any, names: tuple[str, ...]) -> bool:
        for name in names:
            method = getattr(screen, name, None)
            if not callable(method):
                continue
            try:
                method(None)
                return True
            except TypeError:
                try:
                    method()
                    return True
                except Exception:
                    pass
            except Exception:
                pass
        return False

    @staticmethod
    def _elapsed_seconds(screen: Any) -> float | None:
        for attr in (
            "elapsed_seconds",
            "elapsed_time",
            "elapsed",
            "seconds",
        ):
            value = getattr(screen, attr, None)
            if isinstance(value, (int, float)):
                return max(0.0, float(value))

        label = getattr(screen, "time_label", None)
        text = getattr(label, "text", "") if label is not None else ""
        match = re.search(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:\.(\d+))?", str(text))
        if match:
            return (
                int(match.group(1) or 0) * 3600
                + int(match.group(2)) * 60
                + int(match.group(3))
                + float("0." + (match.group(4) or "0"))
            )
        return None

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        total = max(0.0, float(seconds))
        hours = int(total // 3600)
        minutes = int((total % 3600) // 60)
        secs = total % 60
        return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"

    @staticmethod
    def _result(ok: bool, success: str, failure: str, action: str) -> SkillResult:
        return SkillResult(True, success if ok else failure, 1.0, action, {"success": ok})
