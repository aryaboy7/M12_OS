import json
import os
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_VERSION = 1
DEFAULT_MAX_FACTS = 500


class MemoryManager:
    """
    Reliable permanent memory for Ace.

    Desktop:
        <M12 project>/data/memory/permanent.json

    Android / M12:
        writable application-private memory/permanent.json

    This class never changes storage paths during one application run.
    """

    def __init__(
        self,
        memory_file=None,
        max_facts=DEFAULT_MAX_FACTS,
    ):
        self.max_facts = max(10, int(max_facts))
        self._lock = threading.RLock()

        self.memory_file = (
            Path(memory_file).expanduser()
            if memory_file is not None
            else self.default_memory_file()
        )

        self.memory_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._data = self._empty_data()
        self.load()

    @classmethod
    def default_memory_file(cls):
        explicit = os.getenv(
            "M12_MEMORY_DIR",
            "",
        ).strip()

        if explicit:
            return (
                Path(explicit).expanduser()
                / "permanent.json"
            )

        android_private = os.getenv(
            "ANDROID_PRIVATE",
            "",
        ).strip()

        if android_private:
            return (
                Path(android_private)
                / "memory"
                / "permanent.json"
            )

        try:
            from kivy.utils import platform

            if platform == "android":
                from kivy.app import App

                app = App.get_running_app()

                if app is not None:
                    user_data_dir = str(
                        getattr(
                            app,
                            "user_data_dir",
                            "",
                        )
                    ).strip()

                    if user_data_dir:
                        return (
                            Path(user_data_dir)
                            / "memory"
                            / "permanent.json"
                        )
        except Exception:
            pass

        return (
            BASE_DIR
            / "data"
            / "memory"
            / "permanent.json"
        )

    @staticmethod
    def _now():
        return datetime.now(
            timezone.utc
        ).isoformat(
            timespec="seconds"
        )

    def _empty_data(self):
        return {
            "version": MEMORY_VERSION,
            "updated_at": self._now(),
            "facts": [],
        }

    @staticmethod
    def normalize_name(value):
        text = str(value).strip().lower()
        text = "_".join(text.split())

        return "".join(
            character
            for character in text
            if (
                character.isalnum()
                or character in "_-"
            )
        )

    def load(self):
        with self._lock:
            if not self.memory_file.exists():
                self._data = self._empty_data()
                return

            try:
                loaded = json.loads(
                    self.memory_file.read_text(
                        encoding="utf-8"
                    )
                )

                facts = []

                for item in loaded.get(
                    "facts",
                    [],
                ):
                    if not isinstance(item, dict):
                        continue

                    category = self.normalize_name(
                        item.get("category", "")
                    )
                    key = self.normalize_name(
                        item.get("key", "")
                    )
                    value = str(
                        item.get("value", "")
                    ).strip()

                    if not category or not key or not value:
                        continue

                    facts.append(
                        {
                            "category": category,
                            "key": key,
                            "value": value,
                            "created_at": str(
                                item.get(
                                    "created_at",
                                    self._now(),
                                )
                            ),
                            "updated_at": str(
                                item.get(
                                    "updated_at",
                                    self._now(),
                                )
                            ),
                        }
                    )

                self._data = {
                    "version": MEMORY_VERSION,
                    "updated_at": str(
                        loaded.get(
                            "updated_at",
                            self._now(),
                        )
                    ),
                    "facts": facts[-self.max_facts:],
                }

            except (
                OSError,
                json.JSONDecodeError,
                TypeError,
            ) as error:
                print(
                    "Permanent memory load error: "
                    f"{type(error).__name__}: {error}"
                )
                self._backup_damaged_file()
                self._data = self._empty_data()

    def save_fact(
        self,
        category,
        key,
        value,
    ):
        category = self.normalize_name(category)
        key = self.normalize_name(key)
        value = str(value).strip()

        if not category or not key or not value:
            raise ValueError(
                "Category, key, and value are required."
            )

        with self._lock:
            existing = self._find_locked(
                category,
                key,
            )
            now = self._now()

            if existing is None:
                fact = {
                    "category": category,
                    "key": key,
                    "value": value,
                    "created_at": now,
                    "updated_at": now,
                }
                self._data["facts"].append(fact)
                created = True
                updated = False
            else:
                created = False
                updated = existing["value"] != value
                existing["value"] = value
                existing["updated_at"] = now
                fact = existing

            self._data["facts"] = (
                self._data["facts"][
                    -self.max_facts:
                ]
            )
            self._data["updated_at"] = now
            self._save_locked()

            return {
                "created": created,
                "updated": updated,
                "fact": deepcopy(fact),
            }

    def get_fact(
        self,
        category,
        key,
        default=None,
    ):
        category = self.normalize_name(category)
        key = self.normalize_name(key)

        with self._lock:
            fact = self._find_locked(
                category,
                key,
            )

            if fact is None:
                return default

            return fact["value"]

    def _find_locked(
        self,
        category,
        key,
    ):
        for fact in self._data["facts"]:
            if (
                fact["category"] == category
                and fact["key"] == key
            ):
                return fact

        return None

    def list_facts(
        self,
        category=None,
    ):
        normalized_category = (
            None
            if category is None
            else self.normalize_name(category)
        )

        with self._lock:
            return deepcopy(
                [
                    fact
                    for fact in self._data["facts"]
                    if (
                        normalized_category is None
                        or fact["category"]
                        == normalized_category
                    )
                ]
            )

    def search(
        self,
        query,
        limit=20,
    ):
        query = str(query).strip().lower()

        with self._lock:
            matches = []

            for fact in reversed(
                self._data["facts"]
            ):
                searchable = (
                    f"{fact['category']} "
                    f"{fact['key']} "
                    f"{fact['value']}"
                ).lower()

                if not query or query in searchable:
                    matches.append(
                        deepcopy(fact)
                    )

                if len(matches) >= max(
                    1,
                    int(limit),
                ):
                    break

            return matches

    def delete_fact(
        self,
        category,
        key,
    ):
        category = self.normalize_name(category)
        key = self.normalize_name(key)

        with self._lock:
            original = len(
                self._data["facts"]
            )

            self._data["facts"] = [
                fact
                for fact in self._data["facts"]
                if not (
                    fact["category"] == category
                    and fact["key"] == key
                )
            ]

            deleted = (
                len(self._data["facts"])
                < original
            )

            if deleted:
                self._data["updated_at"] = (
                    self._now()
                )
                self._save_locked()

            return deleted

    def clear_all(self):
        with self._lock:
            self._data = self._empty_data()
            self._save_locked()

    def get_prompt_context(
        self,
        limit=50,
    ):
        """
        Return compact permanent-memory context for AI instructions.
        """
        safe_limit = max(
            1,
            int(limit),
        )

        facts = self.list_facts()[
            -safe_limit:
        ]

        if not facts:
            return ""

        lines = [
            "Permanent facts about the user:"
        ]

        for fact in facts:
            lines.append(
                f"- {fact['category']}.{fact['key']}: "
                f"{fact['value']}"
            )

        return "\n".join(lines)

    def diagnostics(self):
        with self._lock:
            return {
                "memory_file": str(
                    self.memory_file
                ),
                "fact_count": len(
                    self._data["facts"]
                ),
                "facts": deepcopy(
                    self._data["facts"]
                ),
            }

    def _save_locked(self):
        self.memory_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = json.dumps(
            self._data,
            ensure_ascii=False,
            indent=2,
        ) + "\n"

        descriptor, temporary_name = (
            tempfile.mkstemp(
                prefix="permanent_",
                suffix=".tmp",
                dir=str(
                    self.memory_file.parent
                ),
            )
        )

        temporary_path = Path(
            temporary_name
        )

        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
            ) as file:
                file.write(payload)
                file.flush()
                os.fsync(
                    file.fileno()
                )

            os.replace(
                temporary_path,
                self.memory_file,
            )

        finally:
            if temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    def _backup_damaged_file(self):
        if not self.memory_file.exists():
            return

        backup = self.memory_file.with_name(
            self.memory_file.name
            + ".damaged-"
            + datetime.now().strftime(
                "%Y%m%d-%H%M%S"
            )
        )

        try:
            os.replace(
                self.memory_file,
                backup,
            )
        except OSError:
            pass


_shared_manager = None
_shared_lock = threading.Lock()


def get_memory_manager():
    global _shared_manager

    if _shared_manager is None:
        with _shared_lock:
            if _shared_manager is None:
                _shared_manager = (
                    MemoryManager()
                )

    return _shared_manager
