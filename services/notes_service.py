import json
import re
from pathlib import Path
from typing import Optional

from services.m12_service import M12Service
from utils.logger import log


BASE_DIR = Path(__file__).resolve().parent.parent
NOTES_DIR = BASE_DIR / "data" / "notes"
TYPES_FILE = BASE_DIR / "config" / "note_types.json"

NOTES_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


class NotesService(M12Service):
    """
    Central service for reading and managing M12 notes.

    NotesScreen, AI plugins, voice commands, and future cloud
    synchronization should all use this service.
    """

    SERVICE_ID = "notes"
    NAME = "Notes"
    VERSION = "1.0"
    DESCRIPTION = "Stores and manages personal notes."

    CAPABILITIES = [
        "create_note",
        "get_note",
        "get_all_notes",
        "update_note",
        "rename_note",
        "delete_note",
        "search_notes",
        "get_note_types",
    ]

    DEFAULT_TYPES = [
        "Personal",
        "Work",
        "Project",
        "Shopping",
        "Idea",
    ]

    def __init__(
        self,
        notes_dir=NOTES_DIR,
        types_file=TYPES_FILE,
    ):
        super().__init__()

        self.notes_dir = Path(notes_dir)
        self.types_file = Path(types_file)

        self.notes_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    # -------------------------------------------------------------
    # Service lifecycle
    # -------------------------------------------------------------
    def start(self):
        self.notes_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.running = True

        log.info(
            "NotesService: started"
        )

    def stop(self):
        self.running = False

        log.info(
            "NotesService: stopped"
        )

    def health_check(self):
        try:
            self.notes_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            return {
                "healthy": self.notes_dir.exists(),
                "notes_directory": str(self.notes_dir),
                "note_count": len(
                    self._get_note_files()
                ),
            }

        except Exception as error:
            return {
                "healthy": False,
                "error": (
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            }

    # -------------------------------------------------------------
    # Note types
    # -------------------------------------------------------------
    def get_note_types(self):
        """
        Return configured note categories.
        """
        try:
            if self.types_file.exists():
                data = json.loads(
                    self.types_file.read_text(
                        encoding="utf-8"
                    )
                )

                if isinstance(data, list):
                    cleaned = []

                    for value in data:
                        note_type = str(
                            value
                        ).strip()

                        if (
                            note_type
                            and note_type not in cleaned
                        ):
                            cleaned.append(
                                note_type
                            )

                    if cleaned:
                        return cleaned

        except Exception as error:
            log.error(
                "NotesService: failed to load types: "
                f"{error}"
            )

        return list(
            self.DEFAULT_TYPES
        )

    # -------------------------------------------------------------
    # Read notes
    # -------------------------------------------------------------
    def get_all_notes(
        self,
        note_type=None,
    ):
        """
        Return all notes, newest first.

        Each returned note contains:

            id
            path
            filename
            title
            type
            body
            modified
        """
        notes = []

        for path in self._get_note_files():
            note = self._read_note_file(
                path
            )

            if note_type:
                requested_type = str(
                    note_type
                ).strip()

                if (
                    requested_type != "All"
                    and note["type"] != requested_type
                ):
                    continue

            notes.append(
                note
            )

        return notes

    def get_note(
        self,
        note_reference,
    ):
        """
        Find one note by:

            Path object
            full path
            filename
            filename without extension
            exact title
        """
        path = self._resolve_note_path(
            note_reference
        )

        if path is None:
            return None

        return self._read_note_file(
            path
        )

    def search_notes(
        self,
        query,
        note_type=None,
    ):
        """
        Search titles, bodies, types, and filenames.
        """
        search_text = str(
            query
        ).strip().lower()

        if not search_text:
            return self.get_all_notes(
                note_type=note_type
            )

        matches = []

        for note in self.get_all_notes(
            note_type=note_type
        ):
            searchable = " ".join(
                [
                    str(note.get("title", "")),
                    str(note.get("type", "")),
                    str(note.get("body", "")),
                    str(note.get("filename", "")),
                ]
            ).lower()

            if search_text in searchable:
                matches.append(
                    note
                )

        return matches

    # -------------------------------------------------------------
    # Create and update notes
    # -------------------------------------------------------------
    def create_note(
        self,
        title,
        body="",
        note_type="Personal",
    ):
        """
        Create a new JSON note.

        If the filename already exists, a number is appended.
        """
        clean_title = str(
            title
        ).strip()

        if not clean_title:
            clean_title = "Untitled"

        clean_body = str(
            body
        )

        clean_type = str(
            note_type
        ).strip()

        if not clean_type:
            clean_type = "Personal"

        path = self._unique_note_path(
            clean_title
        )

        data = {
            "title": clean_title,
            "type": clean_type,
            "body": clean_body,
        }

        self._write_note_file(
            path=path,
            data=data,
        )

        log.info(
            "NotesService: created "
            f"{path.name}"
        )

        return self._read_note_file(
            path
        )

    def update_note(
        self,
        note_reference,
        title=None,
        body=None,
        note_type=None,
    ):
        """
        Update an existing note.

        The note filename remains unchanged unless rename_note()
        is called separately.
        """
        path = self._resolve_note_path(
            note_reference
        )

        if path is None:
            return None

        current = self._read_note_file(
            path
        )

        updated_data = {
            "title": (
                str(title).strip()
                if title is not None
                else current["title"]
            ),
            "type": (
                str(note_type).strip()
                if note_type is not None
                else current["type"]
            ),
            "body": (
                str(body)
                if body is not None
                else current["body"]
            ),
        }

        if not updated_data["title"]:
            updated_data["title"] = path.stem

        if not updated_data["type"]:
            updated_data["type"] = "Personal"

        # Legacy TXT notes become JSON when edited.
        if path.suffix.lower() == ".txt":
            new_path = self._unique_note_path(
                updated_data["title"]
            )

            self._write_note_file(
                path=new_path,
                data=updated_data,
            )

            path.unlink()

            path = new_path

        else:
            self._write_note_file(
                path=path,
                data=updated_data,
            )

        log.info(
            "NotesService: updated "
            f"{path.name}"
        )

        return self._read_note_file(
            path
        )

    def rename_note(
        self,
        note_reference,
        new_title,
    ):
        """
        Change the note title and its JSON filename.
        """
        path = self._resolve_note_path(
            note_reference
        )

        if path is None:
            return None

        clean_title = str(
            new_title
        ).strip()

        if not clean_title:
            raise ValueError(
                "New note title cannot be empty."
            )

        note = self._read_note_file(
            path
        )

        new_path = self._unique_note_path(
            clean_title,
            exclude_path=path,
        )

        data = {
            "title": clean_title,
            "type": note["type"],
            "body": note["body"],
        }

        self._write_note_file(
            path=new_path,
            data=data,
        )

        if path.resolve() != new_path.resolve():
            path.unlink()

        log.info(
            "NotesService: renamed "
            f"{path.name} to {new_path.name}"
        )

        return self._read_note_file(
            new_path
        )

    # -------------------------------------------------------------
    # Delete notes
    # -------------------------------------------------------------
    def delete_note(
        self,
        note_reference,
    ):
        """
        Delete a note.

        Returns True when a note was deleted.
        """
        path = self._resolve_note_path(
            note_reference
        )

        if path is None:
            return False

        try:
            filename = path.name

            path.unlink()

            log.info(
                "NotesService: deleted "
                f"{filename}"
            )

            return True

        except Exception as error:
            log.error(
                "NotesService: failed to delete "
                f"{path}: {error}"
            )

            return False

    # -------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------
    def _get_note_files(self):
        files = (
            list(
                self.notes_dir.glob(
                    "*.json"
                )
            )
            + list(
                self.notes_dir.glob(
                    "*.txt"
                )
            )
        )

        def modified_time(path):
            try:
                return path.stat().st_mtime
            except Exception:
                return 0

        return sorted(
            files,
            key=modified_time,
            reverse=True,
        )

    def _read_note_file(
        self,
        path,
    ):
        path = Path(path)

        try:
            modified = path.stat().st_mtime
        except Exception:
            modified = 0

        if path.suffix.lower() == ".json":
            try:
                data = json.loads(
                    path.read_text(
                        encoding="utf-8"
                    )
                )

                if not isinstance(data, dict):
                    data = {}

                return {
                    "id": path.stem,
                    "path": path,
                    "filename": path.name,
                    "title": str(
                        data.get(
                            "title",
                            path.stem,
                        )
                    ),
                    "type": str(
                        data.get(
                            "type",
                            "Personal",
                        )
                    ),
                    "body": str(
                        data.get(
                            "body",
                            "",
                        )
                    ),
                    "modified": modified,
                }

            except Exception as error:
                log.error(
                    "NotesService: failed to read JSON note "
                    f"{path.name}: {error}"
                )

        try:
            body = path.read_text(
                encoding="utf-8"
            )

        except Exception:
            body = ""

        return {
            "id": path.stem,
            "path": path,
            "filename": path.name,
            "title": path.stem,
            "type": "Personal",
            "body": body,
            "modified": modified,
        }

    def _write_note_file(
        self,
        path,
        data,
    ):
        path = Path(path)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "title": str(
                data.get(
                    "title",
                    path.stem,
                )
            ),
            "type": str(
                data.get(
                    "type",
                    "Personal",
                )
            ),
            "body": str(
                data.get(
                    "body",
                    "",
                )
            ),
        }

        temporary_path = path.with_suffix(
            path.suffix + ".tmp"
        )

        temporary_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary_path.replace(
            path
        )

    def _resolve_note_path(
        self,
        note_reference,
    ) -> Optional[Path]:
        if note_reference is None:
            return None

        if isinstance(
            note_reference,
            Path,
        ):
            candidate = note_reference

            if candidate.exists():
                return candidate

        reference = str(
            note_reference
        ).strip()

        if not reference:
            return None

        candidate = Path(reference)

        if candidate.exists():
            return candidate

        direct_candidate = (
            self.notes_dir / reference
        )

        if direct_candidate.exists():
            return direct_candidate

        reference_lower = reference.lower()

        for path in self._get_note_files():
            note = self._read_note_file(
                path
            )

            if (
                path.name.lower() == reference_lower
                or path.stem.lower() == reference_lower
                or note["title"].strip().lower()
                == reference_lower
            ):
                return path

        return None

    def _safe_filename(
        self,
        title,
    ):
        filename = str(
            title
        ).strip()

        filename = re.sub(
            r'[<>:"/\\|?*\x00-\x1f]',
            "_",
            filename,
        )

        filename = re.sub(
            r"\s+",
            " ",
            filename,
        ).strip(" .")

        if not filename:
            filename = "Untitled"

        return filename

    def _unique_note_path(
        self,
        title,
        exclude_path=None,
    ):
        safe_name = self._safe_filename(
            title
        )

        candidate = (
            self.notes_dir
            / f"{safe_name}.json"
        )

        if exclude_path is not None:
            exclude_path = Path(
                exclude_path
            )

            try:
                if (
                    candidate.resolve()
                    == exclude_path.resolve()
                ):
                    return candidate
            except Exception:
                pass

        if not candidate.exists():
            return candidate

        number = 2

        while True:
            candidate = (
                self.notes_dir
                / f"{safe_name} ({number}).json"
            )

            if exclude_path is not None:
                try:
                    if (
                        candidate.resolve()
                        == exclude_path.resolve()
                    ):
                        return candidate
                except Exception:
                    pass

            if not candidate.exists():
                return candidate

            number += 1