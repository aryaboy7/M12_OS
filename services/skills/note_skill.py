import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from services.skills.base_skill import BaseSkill, SkillResult


BASE_DIR = Path(__file__).resolve().parent.parent.parent
from utils.data_paths import NOTES_DIR
TYPES_FILE = BASE_DIR / "config" / "note_types.json"

DEFAULT_TYPES = [
    "Personal",
    "Work",
    "Project",
    "Shopping",
    "Idea",
]


class NotesSkill(BaseSkill):
    """
    Local M12OS Notes skill.

    Examples:
        Open notes.
        Show shopping notes.
        What notes do I have?
        Find my note about Wi-Fi.
        Open the note about taxes.
        Create a note: Buy milk and eggs.
        Create a shopping note called Groceries: Milk, eggs, bread.
        Take a note.
        Delete my last note.

        Открой заметки.
        Покажи рабочие заметки.
        Какие у меня заметки?
        Найди заметку про Wi-Fi.
        Открой заметку про налоги.
        Создай заметку: Купить молоко и яйца.
        Создай заметку покупок: Молоко, яйца, хлеб.
        Запиши заметку.
    """

    name = "notes"
    priority = 4

    PENDING_TIMEOUT_SECONDS = 300

    OPEN_PHRASES = {
        "open notes",
        "show notes",
        "notes app",
        "go to notes",
        "notes",
        "открой заметки",
        "покажи заметки",
        "заметки",
        "перейди в заметки",
    }

    LIST_PHRASES = {
        "what notes do i have",
        "what nodes do i have",
        "what nose do i have",
        "show my notes",
        "show my nodes",
        "show my nose",
        "list my notes",
        "list my nodes",
        "my notes",
        "my nodes",
        "what are my notes",
        "what are my nodes",
        "какие у меня заметки",
        "покажи мои заметки",
        "мои заметки",
        "список заметок",
    }

    NOTE_WORD_VARIANTS = {
        "note",
        "notes",
        "node",
        "nodes",
        "nose",
        "not",
        "ноут",
        "ноты",
        "заметка",
        "заметки",
        "заметку",
    }

    CREATE_PREFIXES = (
        "create a note",
        "create note",
        "take a note",
        "new note",
        "write a note",
        "make a note",
        "создай заметку",
        "создать заметку",
        "новая заметка",
        "запиши заметку",
        "сделай заметку",
    )

    FIND_PREFIXES = (
        "find my note about ",
        "find note about ",
        "find notes about ",
        "search notes for ",
        "search my notes for ",
        "find ",
        "найди заметку про ",
        "найди заметку о ",
        "найди заметки про ",
        "поиск заметок ",
        "найди ",
    )

    OPEN_NOTE_PREFIXES = (
        "open my note about ",
        "open note about ",
        "open the note about ",
        "open note ",
        "открой заметку про ",
        "открой заметку о ",
        "открой заметку ",
    )

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

    TYPE_ALIASES = {
        "personal": "Personal",
        "private": "Personal",
        "личные": "Personal",
        "личная": "Personal",
        "личную": "Personal",

        "work": "Work",
        "business": "Work",
        "рабочие": "Work",
        "рабочая": "Work",
        "рабочую": "Work",

        "project": "Project",
        "projects": "Project",
        "проект": "Project",
        "проекты": "Project",
        "проектные": "Project",

        "shopping": "Shopping",
        "grocery": "Shopping",
        "groceries": "Shopping",
        "покупки": "Shopping",
        "покупок": "Shopping",
        "список покупок": "Shopping",

        "idea": "Idea",
        "ideas": "Idea",
        "идея": "Idea",
        "идеи": "Idea",
    }

    def __init__(self):
        self._pending_lock = threading.RLock()
        self._pending_note = None

    def can_handle(
        self,
        message: str,
        context: Any,
    ) -> float:
        text = self._normalize(message)

        if not text:
            return 0.0

        if self._has_pending_note():
            if text in self.CANCEL_PHRASES:
                return 1.0

            # A short follow-up is likely the missing note body.
            if len(text.split()) <= 40:
                return 1.0

        if text in self.OPEN_PHRASES:
            return 1.0

        if text in self.LIST_PHRASES:
            return 1.0

        if text.startswith(self.CREATE_PREFIXES):
            return 1.0

        if text.startswith(self.FIND_PREFIXES):
            return 1.0

        if text.startswith(self.OPEN_NOTE_PREFIXES):
            return 1.0

        if self._extract_filter_type(text) is not None:
            if (
                "note" in text
                or "notes" in text
                or "замет" in text
            ):
                return 0.99

        words = set(text.split())

        if (
            words.intersection(
                self.NOTE_WORD_VARIANTS
            )
            or "замет" in text
        ):
            return 0.97

        return 0.0

    def handle(
        self,
        message: str,
        context: Any,
    ) -> SkillResult:
        text = self._normalize(message)
        russian = self._is_russian(text)

        if self._has_pending_note():
            if text in self.CANCEL_PHRASES:
                self._clear_pending_note()

                return SkillResult(
                    handled=True,
                    answer=(
                        "Создание заметки отменено."
                        if russian
                        else "Note creation cancelled."
                    ),
                    confidence=1.0,
                    action="note_cancelled",
                )

            return self._finish_pending_note(
                body=str(message).strip(),
                context=context,
                russian=russian,
            )

        if text in self.OPEN_PHRASES:
            opened = self._open_notes(
                context=context,
                note_type=None,
            )

            return SkillResult(
                handled=True,
                answer=(
                    "Заметки открыты."
                    if russian and opened
                    else "Не удалось открыть заметки."
                    if russian
                    else "Notes opened."
                    if opened
                    else "I couldn't open Notes."
                ),
                confidence=1.0,
                action="open_notes",
                data={"opened": opened},
            )

        note_type = self._extract_filter_type(
            text
        )

        if (
            note_type is not None
            and (
                "show" in text
                or "open" in text
                or "покажи" in text
                or "открой" in text
                or "замет" in text
            )
        ):
            opened = self._open_notes(
                context=context,
                note_type=note_type,
            )

            return SkillResult(
                handled=True,
                answer=(
                    f"Открыты заметки типа {note_type}."
                    if russian and opened
                    else f"Не удалось открыть заметки типа {note_type}."
                    if russian
                    else f"{note_type} notes opened."
                    if opened
                    else f"I couldn't open {note_type} notes."
                ),
                confidence=0.99,
                action="open_notes_filter",
                data={
                    "opened": opened,
                    "note_type": note_type,
                },
            )

        if text in self.LIST_PHRASES:
            notes = self._load_notes()

            return self._list_result(
                notes=notes[:20],
                russian=russian,
                action="notes_list",
            )

        if text.startswith(self.OPEN_NOTE_PREFIXES):
            query = self._remove_prefix(
                text,
                self.OPEN_NOTE_PREFIXES,
            )

            return self._find_or_open_result(
                query=query,
                context=context,
                russian=russian,
                open_first=True,
            )

        if text.startswith(self.FIND_PREFIXES):
            query = self._remove_prefix(
                text,
                self.FIND_PREFIXES,
            )

            return self._find_or_open_result(
                query=query,
                context=context,
                russian=russian,
                open_first=False,
            )

        if text.startswith(self.CREATE_PREFIXES):
            return self._handle_create(
                original_message=str(message).strip(),
                normalized=text,
                context=context,
                russian=russian,
            )

        return SkillResult(handled=False)

    @staticmethod
    def _normalize(message: str) -> str:
        text = str(message).strip().lower()
        text = text.replace("’", "'")
        text = re.sub(
            r"[!?;]+",
            " ",
            text,
        )
        text = re.sub(
            r"\.(?=\s*$)",
            "",
            text,
        )
        text = " ".join(text.split())

        # Common speech-recognition substitutions for "notes".
        # Apply them only inside recognizable Notes commands so
        # ordinary words such as "nose" remain untouched elsewhere.
        note_command_markers = (
            "what ",
            "show ",
            "list ",
            "open ",
            "find ",
            "search ",
            "create ",
            "take ",
            "new ",
            "my ",
        )

        if text.startswith(note_command_markers):
            replacements = {
                " nodes ": " notes ",
                " node ": " note ",
                " nose ": " notes ",
                " not ": " note ",
            }

            padded = f" {text} "

            for source, target in replacements.items():
                padded = padded.replace(
                    source,
                    target,
                )

            text = " ".join(
                padded.split()
            )

        return text

    @staticmethod
    def _is_russian(text: str) -> bool:
        return bool(
            re.search(
                r"[а-яё]",
                text,
                re.IGNORECASE,
            )
        )

    def _has_pending_note(self) -> bool:
        with self._pending_lock:
            if self._pending_note is None:
                return False

            age = time.monotonic() - float(
                self._pending_note.get(
                    "created_at",
                    0,
                )
            )

            if age > self.PENDING_TIMEOUT_SECONDS:
                self._pending_note = None
                return False

            return True

    def _set_pending_note(
        self,
        title: str,
        note_type: str,
    ) -> None:
        with self._pending_lock:
            self._pending_note = {
                "title": title,
                "type": note_type,
                "created_at": time.monotonic(),
            }

    def _clear_pending_note(self) -> None:
        with self._pending_lock:
            self._pending_note = None

    def _finish_pending_note(
        self,
        body: str,
        context: Any,
        russian: bool,
    ) -> SkillResult:
        with self._pending_lock:
            pending = dict(
                self._pending_note or {}
            )
            self._pending_note = None

        title = str(
            pending.get(
                "title",
                "",
            )
        ).strip()

        note_type = str(
            pending.get(
                "type",
                "Personal",
            )
        ).strip() or "Personal"

        body = str(body).strip()

        if not body:
            return SkillResult(
                handled=True,
                answer=(
                    "Текст заметки пуст."
                    if russian
                    else "The note text is empty."
                ),
                confidence=1.0,
                action="note_needs_body",
            )

        if not title:
            title = self._title_from_body(body)

        saved = self._save_note(
            title=title,
            note_type=note_type,
            body=body,
        )

        self._refresh_notes_screen(context)

        return SkillResult(
            handled=True,
            answer=(
                f"Заметка «{title}» сохранена."
                if russian and saved
                else "Не удалось сохранить заметку."
                if russian
                else f'Note "{title}" saved.'
                if saved
                else "I couldn't save the note."
            ),
            confidence=1.0,
            action=(
                "note_created"
                if saved
                else "note_save_error"
            ),
            data={
                "saved": saved,
                "title": title,
                "type": note_type,
            },
        )

    def _handle_create(
        self,
        original_message: str,
        normalized: str,
        context: Any,
        russian: bool,
    ) -> SkillResult:
        body = self._remove_prefix(
            original_message,
            self.CREATE_PREFIXES,
            normalize_before_match=True,
        )

        note_type = (
            self._extract_filter_type(
                normalized
            )
            or "Personal"
        )

        title = ""

        # Examples:
        # Create a note called Router Fix: Replace registry.
        # Создай заметку под названием Покупки: Молоко.
        title_match = re.search(
            (
                r"(?:called|named|title|под названием|с названием)"
                r"\s+([^:]+)"
                r"(?:\s*:\s*(.*))?$"
            ),
            body,
            re.IGNORECASE,
        )

        if title_match:
            title = str(
                title_match.group(1)
            ).strip()

            explicit_body = str(
                title_match.group(2) or ""
            ).strip()

            if explicit_body:
                body = explicit_body
            else:
                body = ""

        else:
            colon_match = re.search(
                r":\s*(.+)$",
                body,
                re.DOTALL,
            )

            if colon_match:
                body = colon_match.group(1).strip()

        body = self._remove_type_words(
            body,
            note_type=note_type,
        ).strip(" :,-")

        if not body:
            self._set_pending_note(
                title=title,
                note_type=note_type,
            )

            return SkillResult(
                handled=True,
                answer=(
                    "Что записать в заметку?"
                    if russian
                    else "What should I write in the note?"
                ),
                confidence=1.0,
                action="note_needs_body",
                data={
                    "title": title,
                    "type": note_type,
                },
            )

        if not title:
            title = self._title_from_body(body)

        saved = self._save_note(
            title=title,
            note_type=note_type,
            body=body,
        )

        self._refresh_notes_screen(context)

        return SkillResult(
            handled=True,
            answer=(
                f"Заметка «{title}» сохранена."
                if russian and saved
                else "Не удалось сохранить заметку."
                if russian
                else f'Note "{title}" saved.'
                if saved
                else "I couldn't save the note."
            ),
            confidence=1.0,
            action=(
                "note_created"
                if saved
                else "note_save_error"
            ),
            data={
                "saved": saved,
                "title": title,
                "type": note_type,
            },
        )

    def _find_or_open_result(
        self,
        query: str,
        context: Any,
        russian: bool,
        open_first: bool,
    ) -> SkillResult:
        query = str(query).strip(" .,:;-")

        if not query:
            return SkillResult(
                handled=True,
                answer=(
                    "Что искать в заметках?"
                    if russian
                    else "What should I search for?"
                ),
                confidence=1.0,
                action="notes_search_needs_query",
            )

        matches = self._search_notes(query)

        if not matches:
            return SkillResult(
                handled=True,
                answer=(
                    f"Заметки по запросу «{query}» не найдены."
                    if russian
                    else f'No notes found for "{query}".'
                ),
                confidence=1.0,
                action="notes_search",
                data={
                    "query": query,
                    "count": 0,
                    "notes": [],
                },
            )

        if open_first:
            opened = self._open_note(
                context=context,
                path=matches[0]["path"],
            )

            title = matches[0]["title"]

            return SkillResult(
                handled=True,
                answer=(
                    f"Открыта заметка «{title}»."
                    if russian and opened
                    else f"Не удалось открыть заметку «{title}»."
                    if russian
                    else f'Opened note "{title}".'
                    if opened
                    else f'I found "{title}", but could not open it.'
                ),
                confidence=1.0,
                action="open_note",
                data={
                    "opened": opened,
                    "query": query,
                    "title": title,
                    "path": str(matches[0]["path"]),
                },
            )

        return self._list_result(
            notes=matches[:10],
            russian=russian,
            action="notes_search",
            query=query,
        )

    @staticmethod
    def _load_types() -> list[str]:
        try:
            if TYPES_FILE.exists():
                data = json.loads(
                    TYPES_FILE.read_text(
                        encoding="utf-8"
                    )
                )

                if isinstance(data, list):
                    values = [
                        str(item).strip()
                        for item in data
                        if str(item).strip()
                    ]

                    if values:
                        return values
        except Exception as error:
            print(
                "NotesSkill type load error: "
                f"{type(error).__name__}: {error}"
            )

        return list(DEFAULT_TYPES)

    def _extract_filter_type(
        self,
        text: str,
    ) -> str | None:
        lowered = self._normalize(text)
        available = self._load_types()

        for note_type in available:
            if note_type.lower() in lowered:
                return note_type

        for alias, canonical in self.TYPE_ALIASES.items():
            if alias in lowered:
                if canonical in available:
                    return canonical

                return canonical

        return None

    @staticmethod
    def _read_note(path: Path) -> dict:
        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(data, dict):
                return {
                    "path": path,
                    "title": str(
                        data.get(
                            "title",
                            path.stem,
                        )
                    ).strip() or path.stem,
                    "type": str(
                        data.get(
                            "type",
                            "Personal",
                        )
                    ).strip() or "Personal",
                    "body": str(
                        data.get(
                            "body",
                            "",
                        )
                    ),
                    "modified": path.stat().st_mtime,
                }
        except Exception:
            pass

        try:
            return {
                "path": path,
                "title": path.stem,
                "type": "Personal",
                "body": path.read_text(
                    encoding="utf-8"
                ),
                "modified": path.stat().st_mtime,
            }
        except Exception:
            return {
                "path": path,
                "title": path.stem,
                "type": "Personal",
                "body": "",
                "modified": 0.0,
            }

    def _load_notes(self) -> list[dict]:
        NOTES_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        paths = list(
            NOTES_DIR.glob("*.json")
        ) + list(
            NOTES_DIR.glob("*.txt")
        )

        notes = [
            self._read_note(path)
            for path in paths
            if path.is_file()
        ]

        notes.sort(
            key=lambda item: item["modified"],
            reverse=True,
        )

        return notes

    def _search_notes(
        self,
        query: str,
    ) -> list[dict]:
        words = [
            word
            for word in self._normalize(
                query
            ).split()
            if len(word) >= 2
        ]

        if not words:
            return []

        ranked = []

        for note in self._load_notes():
            title = self._normalize(
                note["title"]
            )
            note_type = self._normalize(
                note["type"]
            )
            body = self._normalize(
                note["body"]
            )

            searchable = (
                f"{title} {note_type} {body}"
            )

            if not all(
                word in searchable
                for word in words
            ):
                continue

            score = 0

            for word in words:
                if word in title:
                    score += 5
                elif word in note_type:
                    score += 3
                elif word in body:
                    score += 1

            ranked.append(
                (
                    score,
                    note["modified"],
                    note,
                )
            )

        ranked.sort(
            key=lambda item: (
                item[0],
                item[1],
            ),
            reverse=True,
        )

        return [
            item[2]
            for item in ranked
        ]

    @staticmethod
    def _safe_filename(title: str) -> str:
        safe = re.sub(
            r'[\\/:*?"<>|]+',
            "_",
            str(title),
        ).strip(" .")

        return safe or "Untitled"

    def _unique_note_path(
        self,
        title: str,
    ) -> Path:
        base = self._safe_filename(title)
        path = NOTES_DIR / f"{base}.json"

        if not path.exists():
            return path

        counter = 2

        while True:
            candidate = (
                NOTES_DIR
                / f"{base} ({counter}).json"
            )

            if not candidate.exists():
                return candidate

            counter += 1

    def _save_note(
        self,
        title: str,
        note_type: str,
        body: str,
    ) -> bool:
        NOTES_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        data = {
            "title": str(title).strip()
            or "Untitled",
            "type": str(note_type).strip()
            or "Personal",
            "body": str(body),
        }

        path = self._unique_note_path(
            data["title"]
        )

        try:
            path.write_text(
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=4,
                ),
                encoding="utf-8",
            )
            return True

        except OSError as error:
            print(
                "NotesSkill save error: "
                f"{type(error).__name__}: {error}"
            )
            return False

    @staticmethod
    def _title_from_body(body: str) -> str:
        first_line = str(body).strip().splitlines()[0]
        first_line = re.sub(
            r"\s+",
            " ",
            first_line,
        ).strip(" .,:;-")

        if not first_line:
            return "Untitled"

        if len(first_line) > 45:
            return first_line[:42].rstrip() + "..."

        return first_line

    def _list_result(
        self,
        notes: list[dict],
        russian: bool,
        action: str,
        query: str | None = None,
    ) -> SkillResult:
        if not notes:
            return SkillResult(
                handled=True,
                answer=(
                    "Заметок не найдено."
                    if russian
                    else "No notes found."
                ),
                confidence=1.0,
                action=action,
                data={
                    "count": 0,
                    "notes": [],
                    "query": query,
                },
            )

        lines = []
        data_notes = []

        for note in notes:
            title = note["title"]
            note_type = note["type"]

            preview = re.sub(
                r"\s+",
                " ",
                note["body"],
            ).strip()

            if len(preview) > 80:
                preview = (
                    preview[:77].rstrip()
                    + "..."
                )

            line = f"{title} [{note_type}]"

            if preview:
                line += f" — {preview}"

            lines.append(line)

            data_notes.append(
                {
                    "title": title,
                    "type": note_type,
                    "body": note["body"],
                    "path": str(note["path"]),
                }
            )

        if query:
            prefix = (
                f"Найденные заметки по запросу «{query}»:"
                if russian
                else f'Notes found for "{query}":'
            )
        else:
            prefix = (
                "Ваши заметки:"
                if russian
                else "Your notes:"
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
            action=action,
            data={
                "count": len(data_notes),
                "notes": data_notes,
                "query": query,
            },
        )

    @staticmethod
    def _open_notes(
        context: Any,
        note_type: str | None,
    ) -> bool:
        if context is None:
            return False

        if note_type:
            method = getattr(
                context,
                "open_notes_filter",
                None,
            )

            if callable(method):
                try:
                    return bool(
                        method(note_type)
                    )
                except Exception as error:
                    print(
                        "NotesSkill filter open error: "
                        f"{type(error).__name__}: {error}"
                    )

        open_screen = getattr(
            context,
            "open_screen",
            None,
        )

        if not callable(open_screen):
            return False

        try:
            opened = bool(
                open_screen("notes")
            )
        except Exception as error:
            print(
                "NotesSkill open error: "
                f"{type(error).__name__}: {error}"
            )
            return False

        if opened and note_type:
            get_screen = getattr(
                context,
                "get_screen",
                None,
            )

            if callable(get_screen):
                try:
                    screen = get_screen("notes")
                    setter = getattr(
                        screen,
                        "set_filter",
                        None,
                    )

                    if callable(setter):
                        setter(note_type)
                except Exception as error:
                    print(
                        "NotesSkill set_filter error: "
                        f"{type(error).__name__}: {error}"
                    )

        return opened

    @staticmethod
    def _open_note(
        context: Any,
        path: Path,
    ) -> bool:
        if context is None:
            return False

        manager = getattr(
            context,
            "screen_manager",
            None,
        )

        if manager is None:
            return False

        for editor_name in (
            "editor",
            "note_editor",
        ):
            try:
                if not manager.has_screen(
                    editor_name
                ):
                    continue

                editor = manager.get_screen(
                    editor_name
                )

                loader = getattr(
                    editor,
                    "load_note",
                    None,
                )

                if not callable(loader):
                    continue

                loader(path)
                manager.current = editor_name
                return True

            except Exception as error:
                print(
                    "NotesSkill open note error: "
                    f"{type(error).__name__}: {error}"
                )

        return False

    @staticmethod
    def _refresh_notes_screen(
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
            screen = get_screen("notes")
            refresh = getattr(
                screen,
                "refresh_notes",
                None,
            )

            if callable(refresh):
                refresh()

        except Exception:
            pass

    @staticmethod
    def _remove_prefix(
        value: str,
        prefixes: tuple[str, ...],
        normalize_before_match: bool = False,
    ) -> str:
        raw = str(value).strip()
        compare = (
            NotesSkill._normalize(raw)
            if normalize_before_match
            else raw.lower()
        )

        for prefix in sorted(
            prefixes,
            key=len,
            reverse=True,
        ):
            if compare.startswith(prefix):
                # This is safe for the current ASCII/Cyrillic commands:
                # normalization changes punctuation at the end, not prefix size.
                return raw[len(prefix):].strip(
                    " :,-"
                )

        return raw

    @staticmethod
    def _remove_type_words(
        body: str,
        note_type: str,
    ) -> str:
        value = str(body).strip()

        aliases = [
            alias
            for alias, canonical
            in NotesSkill.TYPE_ALIASES.items()
            if canonical == note_type
        ]

        for alias in sorted(
            aliases,
            key=len,
            reverse=True,
        ):
            value = re.sub(
                rf"^(?:a\s+|an\s+)?{re.escape(alias)}\s+",
                "",
                value,
                flags=re.IGNORECASE,
            )

        value = re.sub(
            r"^(?:note|заметку|заметка)\s*",
            "",
            value,
            flags=re.IGNORECASE,
        )

        return value
