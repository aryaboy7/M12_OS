import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from services.skills.base_skill import BaseSkill, SkillResult


BASE_DIR = Path(__file__).resolve().parent.parent.parent
EVENTS_DIR = BASE_DIR / "data" / "events"
EVENTS_FILE = EVENTS_DIR / "events.json"

REMINDER_MINUTES = {
    "Event Time": 0,
    "At time": 0,
    "At event time": 0,
    "5m": 5,
    "5 minutes before": 5,
    "15m": 15,
    "15 minutes before": 15,
    "30m": 30,
    "30 minutes before": 30,
    "1h": 60,
    "1 hour before": 60,
    "1 day": 1440,
    "1 day before": 1440,
}

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

EN_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

RU_WEEKDAYS = {
    "понедельник": 0,
    "понедельника": 0,
    "вторник": 1,
    "вторника": 1,
    "среду": 2,
    "среда": 2,
    "четверг": 3,
    "четверга": 3,
    "пятницу": 4,
    "пятница": 4,
    "субботу": 5,
    "суббота": 5,
    "воскресенье": 6,
}


class ReminderSkill(BaseSkill):
    """Create and read reminders stored in M12OS calendar events."""

    name = "reminder"
    priority = 8
    pending_timeout_seconds = 300

    def __init__(self):
        self._pending_title = None
        self._pending_russian = False
        self._pending_created_at = None

    OPEN_PHRASES = {
        "open reminders",
        "show reminders",
        "open reminder",
        "открой напоминания",
        "покажи напоминания",
    }

    LIST_PHRASES = {
        "what reminders do i have",
        "what reminder do i have",
        "show my reminders",
        "list my reminders",
        "my reminders",
        "do i have any reminders",
        "какие у меня напоминания",
        "покажи мои напоминания",
        "мои напоминания",
        "есть ли у меня напоминания",
    }

    NEXT_PHRASES = {
        "what is my next reminder",
        "what's my next reminder",
        "next reminder",
        "when is my next reminder",
        "какое следующее напоминание",
        "когда следующее напоминание",
    }

    CREATE_PREFIXES = (
        "remind me ",
        "set a reminder ",
        "create a reminder ",
        "напомни мне ",
        "напомни ",
        "создай напоминание ",
        "поставь напоминание ",
    )

    def can_handle(self, message: str, context: Any) -> float:
        text = self._normalize(message)

        if not text:
            return 0.0

        if text in self.OPEN_PHRASES:
            return 1.0

        if text in self.LIST_PHRASES:
            return 1.0

        if text in self.NEXT_PHRASES:
            return 1.0

        if text.startswith(self.CREATE_PREFIXES):
            return 1.0

        if self._has_active_pending():
            if self._extract_time(text) is not None:
                return 1.0
            if self._looks_like_cancel(text):
                return 1.0

        if (
            "reminder" in text
            or "reminders" in text
            or "напоминание" in text
            or "напоминания" in text
            or text.startswith("напомни")
        ):
            return 0.97

        return 0.0

    def handle(self, message: str, context: Any) -> SkillResult:
        text = self._normalize(message)
        russian = self._is_russian(text)

        if text in self.OPEN_PHRASES:
            opened = self._open_calendar(context)
            answer = (
                "Напоминания открыты."
                if russian and opened
                else "Не удалось открыть напоминания."
                if russian
                else "Reminders opened."
                if opened
                else "I couldn't open reminders."
            )
            return SkillResult(
                handled=True,
                answer=answer,
                confidence=1.0,
                action="open_reminders",
                data={"opened": opened},
            )

        events = self._load_events()

        if self._has_active_pending():
            if self._looks_like_cancel(text):
                self._clear_pending()
                return SkillResult(
                    handled=True,
                    answer=(
                        "Хорошо, напоминание отменено."
                        if russian
                        else "Okay, I canceled that reminder."
                    ),
                    confidence=1.0,
                    action="reminder_cancelled",
                )

            pending_result = self._complete_pending_reminder(
                text=text,
                events=events,
            )

            if pending_result is not None:
                return pending_result

        if text in self.NEXT_PHRASES:
            reminders = self._upcoming_reminders(events, limit=1)
            return self._reminder_list_result(
                reminders=reminders,
                russian=russian,
                next_only=True,
            )

        if text in self.LIST_PHRASES:
            reminders = self._upcoming_reminders(events, limit=20)
            return self._reminder_list_result(
                reminders=reminders,
                russian=russian,
                next_only=False,
            )

        if text.startswith(self.CREATE_PREFIXES):
            parsed = self._parse_create_request(text=text, russian=russian)

            if parsed is None:
                pending_title = self._extract_pending_title(text)

                if pending_title:
                    self._set_pending(
                        title=pending_title,
                        russian=russian,
                    )

                    return SkillResult(
                        handled=True,
                        answer=(
                            f"Во сколько напомнить: {pending_title}?"
                            if russian
                            else f"What time should I remind you to {pending_title.lower()}?"
                        ),
                        confidence=1.0,
                        action="reminder_waiting_for_time",
                        data={"title": pending_title},
                    )

                return SkillResult(
                    handled=True,
                    answer=(
                        "Скажите, что напомнить и время. Например: "
                        "«Напомни завтра в 9 утра принять лекарство»."
                        if russian
                        else "Tell me what to remind you about and the time. "
                        "For example: “Remind me tomorrow at 9 AM to take medicine.”"
                    ),
                    confidence=1.0,
                    action="reminder_needs_details",
                )

            title, reminder_dt = parsed
            event = self._make_event(title=title, reminder_dt=reminder_dt)
            events.append(event)

            if not self._save_events(events):
                return SkillResult(
                    handled=True,
                    answer=(
                        "Не удалось сохранить напоминание."
                        if russian
                        else "I couldn't save the reminder."
                    ),
                    confidence=1.0,
                    action="reminder_save_error",
                )

            formatted = self._format_datetime(reminder_dt, russian=russian)
            return SkillResult(
                handled=True,
                answer=(
                    f"Напоминание сохранено: {title}, {formatted}."
                    if russian
                    else f"Reminder saved: {title}, {formatted}."
                ),
                confidence=1.0,
                action="reminder_created",
                data={"title": title, "datetime": reminder_dt.isoformat()},
            )

        return SkillResult(handled=False)

    def _has_active_pending(self) -> bool:
        if not self._pending_title or self._pending_created_at is None:
            return False

        age = (
            datetime.now() - self._pending_created_at
        ).total_seconds()

        if age > self.pending_timeout_seconds:
            self._clear_pending()
            return False

        return True

    def _set_pending(self, title: str, russian: bool) -> None:
        self._pending_title = title
        self._pending_russian = bool(russian)
        self._pending_created_at = datetime.now()

    def _clear_pending(self) -> None:
        self._pending_title = None
        self._pending_russian = False
        self._pending_created_at = None

    @staticmethod
    def _looks_like_cancel(text: str) -> bool:
        return text in {
            "cancel",
            "cancel it",
            "never mind",
            "forget it",
            "отмена",
            "отмени",
            "не надо",
            "забудь",
        }

    def _extract_pending_title(self, text: str) -> str:
        body = text

        for prefix in self.CREATE_PREFIXES:
            if body.startswith(prefix):
                body = body[len(prefix):].strip()
                break

        date_value, date_spans = self._extract_date(body)
        del date_value

        title = self._remove_spans(body, date_spans)
        return self._clean_title(title)

    def _complete_pending_reminder(
        self,
        text: str,
        events: list[dict],
    ) -> SkillResult | None:
        parsed_time = self._extract_time(text)

        if parsed_time is None:
            return None

        reminder_time, time_span = parsed_time
        reminder_date, date_spans = self._extract_date(text)

        if reminder_date is None:
            reminder_date = datetime.now().date()
            candidate = datetime.combine(
                reminder_date,
                reminder_time,
            )

            if candidate <= datetime.now():
                reminder_date += timedelta(days=1)

        reminder_dt = datetime.combine(
            reminder_date,
            reminder_time,
        )

        if reminder_dt <= datetime.now():
            return None

        title = str(self._pending_title).strip()
        russian = self._pending_russian or self._is_russian(text)
        event = self._make_event(
            title=title,
            reminder_dt=reminder_dt,
        )
        events.append(event)

        if not self._save_events(events):
            return SkillResult(
                handled=True,
                answer=(
                    "Не удалось сохранить напоминание."
                    if russian
                    else "I couldn't save the reminder."
                ),
                confidence=1.0,
                action="reminder_save_error",
            )

        self._clear_pending()
        formatted = self._format_datetime(
            reminder_dt,
            russian=russian,
        )

        return SkillResult(
            handled=True,
            answer=(
                f"Напоминание сохранено: {title}, {formatted}."
                if russian
                else f"Reminder saved: {title}, {formatted}."
            ),
            confidence=1.0,
            action="reminder_created",
            data={
                "title": title,
                "datetime": reminder_dt.isoformat(),
            },
        )

    @staticmethod
    def _normalize(message: str) -> str:
        text = str(message).strip().lower().replace("’", "'")
        text = re.sub(r"[^a-z0-9а-яё:'\s,./-]+", " ", text)
        return " ".join(text.split())

    @staticmethod
    def _is_russian(text: str) -> bool:
        return bool(re.search(r"[а-яё]", text, re.IGNORECASE))

    @staticmethod
    def _open_calendar(context: Any) -> bool:
        method = getattr(context, "open_screen", None)
        if not callable(method):
            return False
        try:
            return bool(method("calendar"))
        except Exception as error:
            print(
                "ReminderSkill open error: "
                f"{type(error).__name__}: {error}"
            )
            return False

    @staticmethod
    def _load_events() -> list[dict]:
        if not EVENTS_FILE.exists():
            return []
        try:
            data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(
                "ReminderSkill load error: "
                f"{type(error).__name__}: {error}"
            )
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    @staticmethod
    def _save_events(events: list[dict]) -> bool:
        try:
            EVENTS_DIR.mkdir(parents=True, exist_ok=True)
            EVENTS_FILE.write_text(
                json.dumps(events, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
            return True
        except OSError as error:
            print(
                "ReminderSkill save error: "
                f"{type(error).__name__}: {error}"
            )
            return False

    @staticmethod
    def _make_event(title: str, reminder_dt: datetime) -> dict:
        return {
            "title": title,
            "date": reminder_dt.strftime("%Y-%m-%d"),
            "time": reminder_dt.strftime("%H:%M"),
            "notes": "",
            "reminder": "Event Time",
            "repeat_mode": "once",
            "days": [],
            "until_date": "",
            "last_reminder_date": "",
            "last_event_date": "",
            "reminder_notified": False,
            "event_notified": False,
        }

    def _parse_create_request(
        self,
        text: str,
        russian: bool,
    ) -> tuple[str, datetime] | None:
        body = text
        for prefix in self.CREATE_PREFIXES:
            if body.startswith(prefix):
                body = body[len(prefix):].strip()
                break

        parsed_time = self._extract_time(body)
        if parsed_time is None:
            return None

        reminder_time, time_span = parsed_time
        reminder_date, date_spans = self._extract_date(body)

        if reminder_date is None:
            reminder_date = datetime.now().date()
            candidate = datetime.combine(reminder_date, reminder_time)
            if candidate <= datetime.now():
                reminder_date += timedelta(days=1)

        title = self._remove_spans(body, [time_span, *date_spans])
        title = self._clean_title(title)

        if not title:
            return None

        reminder_dt = datetime.combine(reminder_date, reminder_time)
        if reminder_dt <= datetime.now():
            return None

        return title, reminder_dt

    @staticmethod
    def _extract_time(text: str) -> tuple[time, tuple[int, int]] | None:
        number_words = {
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
            "один": 1,
            "два": 2,
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

        patterns = (
            r"\b(?:at|в)\s+(\d{1,2})(?::(\d{2}))?\s*"
            r"(am|pm|a\.?m\.?|p\.?m\.?|утра|дня|вечера|ночи)?\b",
            r"\b(\d{1,2}):(\d{2})\b",
            r"\b(?:at|в)\s+([a-zа-яё]+)\s*"
            r"(am|pm|a\.?m\.?|p\.?m\.?|утра|дня|вечера|ночи)?\b",
        )

        for pattern_index, pattern in enumerate(patterns):
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            if pattern_index == 2:
                word = str(match.group(1)).lower()
                if word not in number_words:
                    continue
                hour = number_words[word]
                minute = 0
                modifier = str(match.group(2) or "").lower()
            else:
                hour = int(match.group(1))
                minute = int(match.group(2) or 0)
                modifier = ""
                if match.lastindex and match.lastindex >= 3:
                    modifier = str(match.group(3) or "").lower()

            modifier = modifier.replace(".", "")

            if modifier in {"pm", "дня", "вечера"} and hour < 12:
                hour += 12
            if modifier in {"am", "утра"} and hour == 12:
                hour = 0
            if modifier == "ночи" and hour == 12:
                hour = 0

            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return time(hour=hour, minute=minute), match.span()

        return None

    @staticmethod
    def _extract_date(text: str) -> tuple[date | None, list[tuple[int, int]]]:
        now = datetime.now()
        spans = []

        for keyword, offset in (
            ("day after tomorrow", 2),
            ("послезавтра", 2),
            ("tomorrow", 1),
            ("завтра", 1),
            ("today", 0),
            ("сегодня", 0),
        ):
            match = re.search(rf"\b{re.escape(keyword)}\b", text, re.IGNORECASE)
            if match:
                spans.append(match.span())
                return now.date() + timedelta(days=offset), spans

        weekday_map = {**EN_WEEKDAYS, **RU_WEEKDAYS}
        for word, weekday in weekday_map.items():
            match = re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE)
            if not match:
                continue
            days_ahead = (weekday - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            spans.append(match.span())
            return now.date() + timedelta(days=days_ahead), spans

        iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
        if iso_match:
            try:
                result = date(
                    int(iso_match.group(1)),
                    int(iso_match.group(2)),
                    int(iso_match.group(3)),
                )
                spans.append(iso_match.span())
                return result, spans
            except ValueError:
                pass

        us_match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
        if us_match:
            month = int(us_match.group(1))
            day = int(us_match.group(2))
            year_text = us_match.group(3)
            year = int(year_text) if year_text else now.year
            if year < 100:
                year += 2000
            try:
                result = date(year, month, day)
                if year_text is None and result < now.date():
                    result = result.replace(year=year + 1)
                spans.append(us_match.span())
                return result, spans
            except ValueError:
                pass

        return None, spans

    @staticmethod
    def _remove_spans(text: str, spans: list[tuple[int, int]]) -> str:
        chars = list(text)
        for start, end in spans:
            for index in range(max(0, start), min(len(chars), end)):
                chars[index] = " "
        return " ".join("".join(chars).split())

    @staticmethod
    def _clean_title(title: str) -> str:
        value = title.strip(" ,.-")
        value = re.sub(
            r"^(?:to|that i should|чтобы|что нужно|о том что)\s+",
            "",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(
            r"\b(?:on|at|в|во)\s*$",
            "",
            value,
            flags=re.IGNORECASE,
        ).strip(" ,.-")
        if not value:
            return ""
        return value[0].upper() + value[1:]

    @staticmethod
    def _base_datetime(event: dict) -> datetime | None:
        try:
            return datetime.strptime(
                f"{str(event.get('date', '')).strip()} "
                f"{str(event.get('time', '')).strip() or '00:00'}",
                "%Y-%m-%d %H:%M",
            )
        except ValueError:
            return None

    @staticmethod
    def _until_date(event: dict) -> date | None:
        value = str(event.get("until_date", "")).strip()
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None

    def _next_occurrence(self, event: dict, now: datetime) -> datetime | None:
        base = self._base_datetime(event)
        if base is None:
            return None

        mode = str(event.get("repeat_mode", "once")).strip()
        if mode == "once":
            return base if base >= now else None

        until = self._until_date(event)
        for offset in range(0, 370):
            target = now.date() + timedelta(days=offset)
            if target < base.date():
                continue
            if until is not None and target > until:
                return None

            if mode == "every_day":
                candidate = datetime.combine(target, base.time())
            elif mode == "days":
                days = event.get("days", [])
                if not isinstance(days, list):
                    continue
                if DAY_NAMES[target.weekday()] not in days:
                    continue
                candidate = datetime.combine(target, base.time())
            else:
                return None

            if candidate >= now:
                return candidate

        return None

    def _upcoming_reminders(
        self,
        events: list[dict],
        limit: int,
    ) -> list[tuple[datetime, datetime, dict]]:
        now = datetime.now()
        results = []

        for event in events:
            reminder_name = str(event.get("reminder", "None")).strip()
            minutes = REMINDER_MINUTES.get(reminder_name)
            if minutes is None:
                continue

            occurrence = self._next_occurrence(event, now)
            if occurrence is None:
                continue

            notify_at = occurrence - timedelta(minutes=minutes)
            if notify_at < now:
                notify_at = occurrence

            results.append((notify_at, occurrence, event))

        results.sort(key=lambda item: item[0])
        return results[:max(1, int(limit))]

    def _reminder_list_result(
        self,
        reminders: list[tuple[datetime, datetime, dict]],
        russian: bool,
        next_only: bool,
    ) -> SkillResult:
        if not reminders:
            return SkillResult(
                handled=True,
                answer=(
                    "У вас нет предстоящих напоминаний."
                    if russian
                    else "You have no upcoming reminders."
                ),
                confidence=1.0,
                action="reminders_list",
                data={"count": 0, "reminders": []},
            )

        lines = []
        data_items = []

        for notify_at, occurrence, event in reminders:
            title = str(event.get("title", "Untitled Reminder")).strip()
            title = title or "Untitled Reminder"
            formatted = self._format_datetime(notify_at, russian=russian)
            lines.append(f"{formatted}: {title}")
            data_items.append(
                {
                    "title": title,
                    "notify_at": notify_at.isoformat(),
                    "event_at": occurrence.isoformat(),
                    "reminder": str(event.get("reminder", "None")),
                }
            )

        prefix = (
            "Следующее напоминание:"
            if russian and next_only
            else "Ваши предстоящие напоминания:"
            if russian
            else "Your next reminder is:"
            if next_only
            else "Your upcoming reminders:"
        )

        answer = prefix + "\n" + "\n".join(
            f"{index}. {line}"
            for index, line in enumerate(lines, start=1)
        )

        return SkillResult(
            handled=True,
            answer=answer,
            confidence=1.0,
            action="reminders_list",
            data={"count": len(data_items), "reminders": data_items},
        )

    @staticmethod
    def _format_datetime(value: datetime, russian: bool) -> str:
        now = datetime.now()
        if value.date() == now.date():
            day_text = "сегодня" if russian else "today"
        elif value.date() == now.date() + timedelta(days=1):
            day_text = "завтра" if russian else "tomorrow"
        else:
            day_text = value.strftime("%A, %B %-d")

        if russian:
            return f"{day_text} в {value.strftime('%H:%M')}"
        return f"{day_text} at {value.strftime('%-I:%M %p')}"
