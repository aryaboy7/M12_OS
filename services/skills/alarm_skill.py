import json
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from services.skills.base_skill import BaseSkill, SkillResult


BASE_DIR = Path(__file__).resolve().parent.parent.parent
from utils.data_paths import ALARMS_DIR, ALARMS_FILE

DAY_NAMES = [
    "Mon",
    "Tue",
    "Wed",
    "Thu",
    "Fri",
    "Sat",
    "Sun",
]

DAY_ALIASES = {
    "monday": "Mon",
    "mon": "Mon",
    "понедельник": "Mon",
    "понедельникам": "Mon",

    "tuesday": "Tue",
    "tue": "Tue",
    "вторник": "Tue",
    "вторникам": "Tue",

    "wednesday": "Wed",
    "wed": "Wed",
    "среда": "Wed",
    "среду": "Wed",
    "средам": "Wed",

    "thursday": "Thu",
    "thu": "Thu",
    "четверг": "Thu",
    "четвергам": "Thu",

    "friday": "Fri",
    "fri": "Fri",
    "пятница": "Fri",
    "пятницу": "Fri",
    "пятницам": "Fri",

    "saturday": "Sat",
    "sat": "Sat",
    "суббота": "Sat",
    "субботу": "Sat",
    "субботам": "Sat",

    "sunday": "Sun",
    "sun": "Sun",
    "воскресенье": "Sun",
    "воскресеньям": "Sun",
}

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
    "eleven": 11,
    "twelve": 12,

    "ноль": 0,
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
    "одиннадцать": 11,
    "двенадцать": 12,
}


class AlarmSkill(BaseSkill):
    """
    Local M12OS alarm control.

    Examples:
        Open alarms.
        Set an alarm for 7 AM.
        Set an alarm for 6:30 every day.
        Set an alarm for 8 AM on weekdays.
        What alarms do I have?
        Turn off all alarms.
        Turn on all alarms.
        Delete all alarms.

        Открой будильники.
        Поставь будильник на 7 утра.
        Поставь будильник на 6:30 каждый день.
        Поставь будильник на 8 утра по будням.
        Какие у меня будильники?
        Выключи все будильники.
    """

    name = "alarm"
    priority = 3

    PENDING_TIMEOUT_SECONDS = 300

    OPEN_PHRASES = {
        "open alarm",
        "open alarms",
        "show alarms",
        "alarm app",
        "alarms",
        "открой будильник",
        "открой будильники",
        "покажи будильники",
        "будильники",
    }

    LIST_PHRASES = {
        "what alarms do i have",
        "what alarm do i have",
        "show my alarms",
        "list my alarms",
        "my alarms",
        "are any alarms set",
        "какие у меня будильники",
        "покажи мои будильники",
        "мои будильники",
        "есть ли у меня будильники",
    }

    CREATE_PREFIXES = (
        "set an alarm",
        "set alarm",
        "create an alarm",
        "create alarm",
        "wake me",
        "поставь будильник",
        "установи будильник",
        "создай будильник",
        "разбуди меня",
    )

    DISABLE_ALL_PHRASES = {
        "turn off all alarms",
        "disable all alarms",
        "switch off all alarms",
        "выключи все будильники",
        "отключи все будильники",
    }

    ENABLE_ALL_PHRASES = {
        "turn on all alarms",
        "enable all alarms",
        "switch on all alarms",
        "включи все будильники",
    }

    DELETE_ALL_PHRASES = {
        "delete all alarms",
        "remove all alarms",
        "clear all alarms",
        "удали все будильники",
        "очисти все будильники",
    }

    CANCEL_PHRASES = {
        "cancel",
        "cancel it",
        "never mind",
        "forget it",
        "отмена",
        "отмени",
        "не надо",
        "забудь",
    }

    ALARM_WORD_VARIANTS = {
        "alarm",
        "alarms",
        "будильник",
        "будильники",
        "будильника",
    }

    def __init__(self):
        self._pending_lock = threading.RLock()
        self._pending_alarm = None

    def can_handle(
        self,
        message: str,
        context: Any,
    ) -> float:
        text = self._normalize(message)

        if not text:
            return 0.0

        if self._has_pending_alarm():
            if text in self.CANCEL_PHRASES:
                return 1.0

            if self._extract_time(text) is not None:
                return 1.0

        if (
            text in self.OPEN_PHRASES
            or text in self.LIST_PHRASES
            or text in self.DISABLE_ALL_PHRASES
            or text in self.ENABLE_ALL_PHRASES
            or text in self.DELETE_ALL_PHRASES
        ):
            return 1.0

        if text.startswith(self.CREATE_PREFIXES):
            return 1.0

        words = set(text.split())

        if words.intersection(self.ALARM_WORD_VARIANTS):
            return 0.98

        return 0.0

    def handle(
        self,
        message: str,
        context: Any,
    ) -> SkillResult:
        text = self._normalize(message)
        russian = self._is_russian(text)

        if self._has_pending_alarm():
            if text in self.CANCEL_PHRASES:
                self._clear_pending_alarm()

                return SkillResult(
                    handled=True,
                    answer=(
                        "Создание будильника отменено."
                        if russian
                        else "Alarm creation cancelled."
                    ),
                    confidence=1.0,
                    action="alarm_cancelled",
                )

            parsed_time = self._extract_time(text)

            if parsed_time is not None:
                pending = self._take_pending_alarm()
                repeat_mode, days = self._extract_repeat(
                    text
                )

                if repeat_mode == "once":
                    repeat_mode = pending.get(
                        "repeat_mode",
                        "once",
                    )
                    days = pending.get(
                        "days",
                        [],
                    )

                return self._create_alarm_result(
                    hour=parsed_time[0],
                    minute=parsed_time[1],
                    repeat_mode=repeat_mode,
                    days=days,
                    context=context,
                    russian=russian,
                )

        if text in self.OPEN_PHRASES:
            opened = self._open_alarm_screen(
                context
            )

            return SkillResult(
                handled=True,
                answer=(
                    "Будильники открыты."
                    if russian and opened
                    else "Не удалось открыть будильники."
                    if russian
                    else "Alarms opened."
                    if opened
                    else "I couldn't open Alarms."
                ),
                confidence=1.0,
                action="open_alarms",
                data={"opened": opened},
            )

        if text in self.LIST_PHRASES:
            return self._list_result(
                alarms=self._load_alarms(),
                russian=russian,
            )

        if text in self.DISABLE_ALL_PHRASES:
            return self._set_all_enabled_result(
                enabled=False,
                context=context,
                russian=russian,
            )

        if text in self.ENABLE_ALL_PHRASES:
            return self._set_all_enabled_result(
                enabled=True,
                context=context,
                russian=russian,
            )

        if text in self.DELETE_ALL_PHRASES:
            saved = self._save_alarms([])
            self._refresh_alarm_screen(context)

            return SkillResult(
                handled=True,
                answer=(
                    "Все будильники удалены."
                    if russian and saved
                    else "Не удалось удалить будильники."
                    if russian
                    else "All alarms deleted."
                    if saved
                    else "I couldn't delete the alarms."
                ),
                confidence=1.0,
                action="alarms_deleted",
                data={"saved": saved},
            )

        if text.startswith(self.CREATE_PREFIXES):
            parsed_time = self._extract_time(text)
            repeat_mode, days = self._extract_repeat(
                text
            )

            if parsed_time is None:
                self._set_pending_alarm(
                    repeat_mode=repeat_mode,
                    days=days,
                )

                return SkillResult(
                    handled=True,
                    answer=(
                        "На какое время поставить будильник?"
                        if russian
                        else "What time should I set the alarm for?"
                    ),
                    confidence=1.0,
                    action="alarm_needs_time",
                    data={
                        "repeat_mode": repeat_mode,
                        "days": days,
                    },
                )

            return self._create_alarm_result(
                hour=parsed_time[0],
                minute=parsed_time[1],
                repeat_mode=repeat_mode,
                days=days,
                context=context,
                russian=russian,
            )

        return SkillResult(handled=False)

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

    def _has_pending_alarm(self) -> bool:
        with self._pending_lock:
            if self._pending_alarm is None:
                return False

            age = time.monotonic() - float(
                self._pending_alarm.get(
                    "created_at",
                    0,
                )
            )

            if age > self.PENDING_TIMEOUT_SECONDS:
                self._pending_alarm = None
                return False

            return True

    def _set_pending_alarm(
        self,
        repeat_mode: str,
        days: list[str],
    ) -> None:
        with self._pending_lock:
            self._pending_alarm = {
                "repeat_mode": repeat_mode,
                "days": list(days),
                "created_at": time.monotonic(),
            }

    def _clear_pending_alarm(self) -> None:
        with self._pending_lock:
            self._pending_alarm = None

    def _take_pending_alarm(self) -> dict:
        with self._pending_lock:
            value = dict(
                self._pending_alarm or {}
            )
            self._pending_alarm = None
            return value

    @classmethod
    def _replace_number_words(
        cls,
        text: str,
    ) -> str:
        value = text

        for word, number in sorted(
            NUMBER_WORDS.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            value = re.sub(
                rf"\b{re.escape(word)}\b",
                str(number),
                value,
                flags=re.IGNORECASE,
            )

        return value

    @classmethod
    def _extract_time(
        cls,
        text: str,
    ) -> tuple[int, int] | None:
        value = cls._replace_number_words(
            text
        )

        patterns = (
            (
                r"\b(?:at|for|на|в)\s+"
                r"(\d{1,2})"
                r"(?::(\d{2}))?"
                r"\s*(am|pm|a\.m\.|p\.m\.|утра|дня|вечера|ночи)?\b"
            ),
            (
                r"\b(\d{1,2}):(\d{2})"
                r"\s*(am|pm|утра|дня|вечера|ночи)?\b"
            ),
            (
                r"\b(\d{1,2})\s*"
                r"(am|pm|утра|дня|вечера|ночи)\b"
            ),
        )

        for pattern in patterns:
            match = re.search(
                pattern,
                value,
                re.IGNORECASE,
            )

            if not match:
                continue

            hour = int(match.group(1))
            minute = 0
            modifier = ""

            groups = match.groups()

            if len(groups) >= 2:
                second = groups[1]

                if (
                    second is not None
                    and str(second).isdigit()
                ):
                    minute = int(second)

            if len(groups) >= 3:
                modifier = str(
                    groups[2] or ""
                ).lower()
            elif len(groups) == 2:
                second = str(
                    groups[1] or ""
                ).lower()

                if not second.isdigit():
                    modifier = second

            if modifier in {
                "pm",
                "p.m.",
                "дня",
                "вечера",
            }:
                if hour < 12:
                    hour += 12

            elif modifier in {
                "am",
                "a.m.",
                "утра",
            }:
                if hour == 12:
                    hour = 0

            elif modifier == "ночи":
                if hour == 12:
                    hour = 0

            if (
                0 <= hour <= 23
                and 0 <= minute <= 59
            ):
                return hour, minute

        return None

    @staticmethod
    def _extract_repeat(
        text: str,
    ) -> tuple[str, list[str]]:
        if any(
            phrase in text
            for phrase in (
                "every day",
                "daily",
                "each day",
                "каждый день",
                "ежедневно",
            )
        ):
            return "every_day", []

        if any(
            phrase in text
            for phrase in (
                "weekdays",
                "weekday",
                "workdays",
                "по будням",
                "в будни",
            )
        ):
            return (
                "days",
                ["Mon", "Tue", "Wed", "Thu", "Fri"],
            )

        if any(
            phrase in text
            for phrase in (
                "weekends",
                "weekend",
                "по выходным",
                "в выходные",
            )
        ):
            return "days", ["Sat", "Sun"]

        selected = []

        for alias, day_name in DAY_ALIASES.items():
            if re.search(
                rf"\b{re.escape(alias)}\b",
                text,
                re.IGNORECASE,
            ):
                if day_name not in selected:
                    selected.append(day_name)

        selected.sort(
            key=DAY_NAMES.index
        )

        if selected:
            return "days", selected

        return "once", []

    @staticmethod
    def _load_alarms() -> list[dict]:
        if not ALARMS_FILE.exists():
            return []

        try:
            data = json.loads(
                ALARMS_FILE.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            print(
                "AlarmSkill load error: "
                f"{type(error).__name__}: {error}"
            )
            return []

        if not isinstance(data, list):
            return []

        return [
            alarm
            for alarm in data
            if isinstance(alarm, dict)
        ]

    @staticmethod
    def _save_alarms(
        alarms: list[dict],
    ) -> bool:
        try:
            ALARMS_DIR.mkdir(
                parents=True,
                exist_ok=True,
            )

            ALARMS_FILE.write_text(
                json.dumps(
                    alarms,
                    ensure_ascii=False,
                    indent=4,
                ),
                encoding="utf-8",
            )
            return True

        except OSError as error:
            print(
                "AlarmSkill save error: "
                f"{type(error).__name__}: {error}"
            )
            return False

    @staticmethod
    def _new_alarm(
        hour: int,
        minute: int,
        repeat_mode: str,
        days: list[str],
    ) -> dict:
        return {
            "hour": int(hour),
            "minute": int(minute),
            "enabled": True,
            "repeat_mode": repeat_mode,
            "days": list(days),
            "until_date": "",
            "last_fired_date": "",
            "last_fired_time": "",
        }

    def _create_alarm_result(
        self,
        hour: int,
        minute: int,
        repeat_mode: str,
        days: list[str],
        context: Any,
        russian: bool,
    ) -> SkillResult:
        alarms = self._load_alarms()

        alarm = self._new_alarm(
            hour=hour,
            minute=minute,
            repeat_mode=repeat_mode,
            days=days,
        )

        alarms.append(alarm)
        saved = self._save_alarms(alarms)

        self._refresh_alarm_screen(context)
        self._refresh_clock_screen(context)

        time_text = self._format_time(
            hour=hour,
            minute=minute,
            russian=russian,
        )
        repeat_text = self._repeat_text(
            repeat_mode=repeat_mode,
            days=days,
            russian=russian,
        )

        return SkillResult(
            handled=True,
            answer=(
                f"Будильник установлен на {time_text}, {repeat_text}."
                if russian and saved
                else "Не удалось сохранить будильник."
                if russian
                else f"Alarm set for {time_text}, {repeat_text}."
                if saved
                else "I couldn't save the alarm."
            ),
            confidence=1.0,
            action=(
                "alarm_created"
                if saved
                else "alarm_save_error"
            ),
            data={
                "saved": saved,
                "hour": hour,
                "minute": minute,
                "repeat_mode": repeat_mode,
                "days": days,
            },
        )

    def _set_all_enabled_result(
        self,
        enabled: bool,
        context: Any,
        russian: bool,
    ) -> SkillResult:
        alarms = self._load_alarms()

        if not alarms:
            return SkillResult(
                handled=True,
                answer=(
                    "Будильников нет."
                    if russian
                    else "You have no alarms."
                ),
                confidence=1.0,
                action="alarms_enabled",
                data={
                    "enabled": enabled,
                    "count": 0,
                },
            )

        for alarm in alarms:
            alarm["enabled"] = enabled

            if enabled:
                alarm["last_fired_date"] = ""
                alarm["last_fired_time"] = ""

        saved = self._save_alarms(alarms)

        self._refresh_alarm_screen(context)
        self._refresh_clock_screen(context)

        if russian:
            answer = (
                "Все будильники включены."
                if enabled and saved
                else "Все будильники выключены."
                if saved
                else "Не удалось изменить будильники."
            )
        else:
            answer = (
                "All alarms enabled."
                if enabled and saved
                else "All alarms disabled."
                if saved
                else "I couldn't update the alarms."
            )

        return SkillResult(
            handled=True,
            answer=answer,
            confidence=1.0,
            action="alarms_enabled",
            data={
                "saved": saved,
                "enabled": enabled,
                "count": len(alarms),
            },
        )

    def _list_result(
        self,
        alarms: list[dict],
        russian: bool,
    ) -> SkillResult:
        if not alarms:
            return SkillResult(
                handled=True,
                answer=(
                    "У вас нет будильников."
                    if russian
                    else "You have no alarms."
                ),
                confidence=1.0,
                action="alarms_list",
                data={
                    "count": 0,
                    "alarms": [],
                },
            )

        lines = []
        data_items = []

        for alarm in alarms[:20]:
            hour = int(
                alarm.get(
                    "hour",
                    0,
                )
            )
            minute = int(
                alarm.get(
                    "minute",
                    0,
                )
            )
            enabled = bool(
                alarm.get(
                    "enabled",
                    False,
                )
            )
            repeat_mode = str(
                alarm.get(
                    "repeat_mode",
                    "once",
                )
            )
            days = alarm.get(
                "days",
                [],
            )

            if not isinstance(days, list):
                days = []

            status = (
                "включен"
                if russian and enabled
                else "выключен"
                if russian
                else "on"
                if enabled
                else "off"
            )

            line = (
                f"{self._format_time(hour, minute, russian)}, "
                f"{self._repeat_text(repeat_mode, days, russian)}, "
                f"{status}"
            )

            lines.append(line)

            data_items.append(
                {
                    "hour": hour,
                    "minute": minute,
                    "enabled": enabled,
                    "repeat_mode": repeat_mode,
                    "days": list(days),
                }
            )

        prefix = (
            "Ваши будильники:"
            if russian
            else "Your alarms:"
        )

        answer = prefix + "\n" + "\n".join(
            f"{index}. {line}"
            for index, line in enumerate(
                lines,
                start=1,
            )
        )

        return SkillResult(
            handled=True,
            answer=answer,
            confidence=1.0,
            action="alarms_list",
            data={
                "count": len(data_items),
                "alarms": data_items,
            },
        )

    @staticmethod
    def _format_time(
        hour: int,
        minute: int,
        russian: bool,
    ) -> str:
        if russian:
            return f"{hour:02d}:{minute:02d}"

        value = datetime.now().replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        return value.strftime(
            "%-I:%M %p"
        )

    @staticmethod
    def _repeat_text(
        repeat_mode: str,
        days: list[str],
        russian: bool,
    ) -> str:
        if repeat_mode == "every_day":
            return (
                "каждый день"
                if russian
                else "every day"
            )

        if repeat_mode == "days":
            if days == [
                "Mon",
                "Tue",
                "Wed",
                "Thu",
                "Fri",
            ]:
                return (
                    "по будням"
                    if russian
                    else "on weekdays"
                )

            if days == ["Sat", "Sun"]:
                return (
                    "по выходным"
                    if russian
                    else "on weekends"
                )

            joined = ", ".join(days)

            return (
                f"по дням: {joined}"
                if russian
                else f"on {joined}"
            )

        return (
            "один раз"
            if russian
            else "once"
        )

    @staticmethod
    def _open_alarm_screen(
        context: Any,
    ) -> bool:
        if context is None:
            return False

        open_screen = getattr(
            context,
            "open_screen",
            None,
        )

        if not callable(open_screen):
            return False

        try:
            return bool(
                open_screen("alarm")
            )
        except Exception as error:
            print(
                "AlarmSkill open error: "
                f"{type(error).__name__}: {error}"
            )
            return False

    @staticmethod
    def _refresh_alarm_screen(
        context: Any,
    ) -> None:
        if context is None:
            return

        get_screen = getattr(
            context,
            "get_screen",
            None,
        )

        if not callable(get_screen):
            return

        try:
            screen = get_screen("alarm")
            loader = getattr(
                screen,
                "load_alarms",
                None,
            )

            if callable(loader):
                loader()
        except Exception:
            pass

    @staticmethod
    def _refresh_clock_screen(
        context: Any,
    ) -> None:
        if context is None:
            return

        get_screen = getattr(
            context,
            "get_screen",
            None,
        )

        if not callable(get_screen):
            return

        try:
            screen = get_screen("clock")
            refresh = getattr(
                screen,
                "refresh_alarm_info",
                None,
            )

            if callable(refresh):
                refresh()
        except Exception:
            pass
