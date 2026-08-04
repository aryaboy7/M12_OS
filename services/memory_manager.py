import json
import os
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

MEMORY_VERSION = 2
DEFAULT_MAX_FACTS = 500


class MemoryManager:
    """
    Structured permanent memory for Ace.

    Storage format version 2:

    {
      "version": 2,
      "updated_at": "...",
      "profile": {...},
      "family": {...},
      "likes": [...],
      "personal": {...},
      "other": {...},
      "_meta": {...}
    }

    Compatibility:
        Existing callers can continue using:
            save_fact(category, key, value)
            get_fact(category, key)
            list_facts()
            search()
            delete_fact()
            get_prompt_context()

    Existing version-1 flat memory files are migrated automatically.
    """

    FAMILY_STORAGE_ALIASES = {
        "wife_name": "wife",
        "husband_name": "husband",
        "daughter_name": "daughter",
        "son_name": "son",
        "mother_name": "mother",
        "father_name": "father",
        "sister_name": "sister",
        "brother_name": "brother",
        "granddaughter_name": "granddaughter",
        "grandson_name": "grandson",
        "son_in_law_name": "son_in_law",
        "daughter_in_law_name": "daughter_in_law",
    }

    FAMILY_PUBLIC_ALIASES = {
        value: key
        for key, value in FAMILY_STORAGE_ALIASES.items()
    }

    PROFILE_STORAGE_ALIASES = {
        "favorite_language": "favorite_language",
        "son_in_law": "son_in_law",
    }

    def __init__(
        self,
        memory_file=None,
        max_facts=DEFAULT_MAX_FACTS,
    ):
        self.max_facts = max(
            10,
            int(max_facts),
        )
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
            "profile": {},
            "family": {},
            "likes": [],
            "personal": {},
            "other": {},
            "_meta": {},
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
        """
        Load memory and migrate version-1 files automatically.
        """
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

                if not isinstance(
                    loaded,
                    dict,
                ):
                    raise TypeError(
                        "Permanent memory root must be an object."
                    )

                version = int(
                    loaded.get(
                        "version",
                        1,
                    )
                )

                if (
                    version == 1
                    or "facts" in loaded
                ):
                    self._data = (
                        self._migrate_v1_locked(
                            loaded
                        )
                    )
                    self._save_locked()
                    return

                self._data = (
                    self._validate_v2_locked(
                        loaded
                    )
                )

            except (
                OSError,
                json.JSONDecodeError,
                TypeError,
                ValueError,
            ) as error:
                print(
                    "Permanent memory load error: "
                    f"{type(error).__name__}: {error}"
                )
                self._backup_damaged_file()
                self._data = self._empty_data()

    def _validate_v2_locked(
        self,
        loaded,
    ):
        data = self._empty_data()

        data["updated_at"] = str(
            loaded.get(
                "updated_at",
                self._now(),
            )
        )

        for section in (
            "profile",
            "family",
            "personal",
        ):
            source = loaded.get(
                section,
                {},
            )

            if isinstance(source, dict):
                data[section] = {
                    self.normalize_name(key): str(
                        value
                    ).strip()
                    for key, value in source.items()
                    if (
                        self.normalize_name(key)
                        and str(value).strip()
                    )
                }

        likes = loaded.get(
            "likes",
            [],
        )

        if isinstance(likes, list):
            clean_likes = []

            for value in likes:
                text = str(value).strip()

                if (
                    text
                    and text.lower()
                    not in {
                        item.lower()
                        for item in clean_likes
                    }
                ):
                    clean_likes.append(text)

            data["likes"] = clean_likes

        other = loaded.get(
            "other",
            {},
        )

        if isinstance(other, dict):
            clean_other = {}

            for category, values in other.items():
                clean_category = (
                    self.normalize_name(
                        category
                    )
                )

                if (
                    not clean_category
                    or not isinstance(
                        values,
                        dict,
                    )
                ):
                    continue

                clean_values = {
                    self.normalize_name(key): str(
                        value
                    ).strip()
                    for key, value in values.items()
                    if (
                        self.normalize_name(key)
                        and str(value).strip()
                    )
                }

                if clean_values:
                    clean_other[
                        clean_category
                    ] = clean_values

            data["other"] = clean_other

        metadata = loaded.get(
            "_meta",
            {},
        )

        if isinstance(metadata, dict):
            data["_meta"] = deepcopy(
                metadata
            )

        return data

    def _migrate_v1_locked(
        self,
        loaded,
    ):
        """
        Convert the old flat facts list to version 2.
        """
        data = self._empty_data()

        facts = loaded.get(
            "facts",
            [],
        )

        if not isinstance(facts, list):
            facts = []

        for item in facts:
            if not isinstance(item, dict):
                continue

            category = self.normalize_name(
                item.get(
                    "category",
                    "",
                )
            )
            key = self.normalize_name(
                item.get(
                    "key",
                    "",
                )
            )
            value = str(
                item.get(
                    "value",
                    "",
                )
            ).strip()

            if (
                not category
                or not key
                or not value
            ):
                continue

            self._store_value_locked(
                data=data,
                category=category,
                key=key,
                value=value,
                created_at=str(
                    item.get(
                        "created_at",
                        self._now(),
                    )
                ),
                updated_at=str(
                    item.get(
                        "updated_at",
                        self._now(),
                    )
                ),
            )

        data["updated_at"] = str(
            loaded.get(
                "updated_at",
                self._now(),
            )
        )

        return data

    def save_fact(
        self,
        category,
        key,
        value,
    ):
        category = self.normalize_name(
            category
        )
        key = self.normalize_name(
            key
        )
        value = str(value).strip()

        if (
            not category
            or not key
            or not value
        ):
            raise ValueError(
                "Category, key, and value are required."
            )

        with self._lock:
            existing_value = self.get_fact(
                category,
                key,
                default=None,
            )

            now = self._now()
            created = (
                existing_value is None
            )
            updated = (
                existing_value is not None
                and existing_value != value
            )

            created_at = now

            existing_meta = (
                self._data["_meta"].get(
                    self._meta_id(
                        category,
                        key,
                    ),
                    {},
                )
            )

            if existing_meta:
                created_at = str(
                    existing_meta.get(
                        "created_at",
                        now,
                    )
                )

            self._store_value_locked(
                data=self._data,
                category=category,
                key=key,
                value=value,
                created_at=created_at,
                updated_at=now,
            )

            self._data["updated_at"] = now
            self._save_locked()

            return {
                "created": created,
                "updated": updated,
                "fact": {
                    "category": category,
                    "key": key,
                    "value": value,
                    "created_at": created_at,
                    "updated_at": now,
                },
            }

    def _store_value_locked(
        self,
        data,
        category,
        key,
        value,
        created_at,
        updated_at,
    ):
        storage_section, storage_key = (
            self._storage_location(
                category,
                key,
            )
        )

        if storage_section == "likes":
            existing_index = None

            for index, item in enumerate(
                data["likes"]
            ):
                if (
                    self.normalize_name(
                        item
                    )
                    == self.normalize_name(
                        key
                    )
                    or item.lower()
                    == value.lower()
                ):
                    existing_index = index
                    break

            if existing_index is None:
                data["likes"].append(
                    value
                )
            else:
                data["likes"][
                    existing_index
                ] = value

        elif storage_section in {
            "profile",
            "family",
            "personal",
        }:
            data[storage_section][
                storage_key
            ] = value

        else:
            category_bucket = (
                data["other"].setdefault(
                    storage_section,
                    {},
                )
            )
            category_bucket[
                storage_key
            ] = value

        data["_meta"][
            self._meta_id(
                category,
                key,
            )
        ] = {
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def get_fact(
        self,
        category,
        key,
        default=None,
    ):
        category = self.normalize_name(
            category
        )
        key = self.normalize_name(
            key
        )

        with self._lock:
            section, storage_key = (
                self._storage_location(
                    category,
                    key,
                )
            )

            if section == "likes":
                for item in self._data[
                    "likes"
                ]:
                    if (
                        self.normalize_name(
                            item
                        )
                        == self.normalize_name(
                            key
                        )
                    ):
                        return item

                return default

            if section in {
                "profile",
                "family",
                "personal",
            }:
                return self._data[
                    section
                ].get(
                    storage_key,
                    default,
                )

            return self._data[
                "other"
            ].get(
                section,
                {},
            ).get(
                storage_key,
                default,
            )

    def list_facts(
        self,
        category=None,
    ):
        """
        Return version-1-compatible fact dictionaries.
        """
        normalized_category = (
            None
            if category is None
            else self.normalize_name(
                category
            )
        )

        with self._lock:
            facts = []

            for key, value in self._data[
                "profile"
            ].items():
                facts.append(
                    self._fact_record(
                        "profile",
                        key,
                        value,
                    )
                )

            for key, value in self._data[
                "family"
            ].items():
                public_key = (
                    self.FAMILY_PUBLIC_ALIASES.get(
                        key,
                        key,
                    )
                )

                facts.append(
                    self._fact_record(
                        "family",
                        public_key,
                        value,
                    )
                )

            for value in self._data[
                "likes"
            ]:
                key = self.normalize_name(
                    value
                )

                facts.append(
                    self._fact_record(
                        "likes",
                        key,
                        value,
                    )
                )

            for key, value in self._data[
                "personal"
            ].items():
                facts.append(
                    self._fact_record(
                        "personal",
                        key,
                        value,
                    )
                )

            for other_category, values in (
                self._data["other"].items()
            ):
                for key, value in values.items():
                    facts.append(
                        self._fact_record(
                            other_category,
                            key,
                            value,
                        )
                    )

            if normalized_category is not None:
                facts = [
                    fact
                    for fact in facts
                    if fact["category"]
                    == normalized_category
                ]

            return facts[
                -self.max_facts:
            ]

    def _fact_record(
        self,
        category,
        key,
        value,
    ):
        metadata = self._data[
            "_meta"
        ].get(
            self._meta_id(
                category,
                key,
            ),
            {},
        )

        return {
            "category": category,
            "key": key,
            "value": value,
            "created_at": str(
                metadata.get(
                    "created_at",
                    self._data[
                        "updated_at"
                    ],
                )
            ),
            "updated_at": str(
                metadata.get(
                    "updated_at",
                    self._data[
                        "updated_at"
                    ],
                )
            ),
        }

    def search(
        self,
        query,
        limit=20,
    ):
        query = str(
            query
        ).strip().lower()

        matches = []

        for fact in reversed(
            self.list_facts()
        ):
            searchable = (
                f"{fact['category']} "
                f"{fact['key']} "
                f"{fact['value']}"
            ).lower()

            if (
                not query
                or query in searchable
            ):
                matches.append(
                    fact
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
        category = self.normalize_name(
            category
        )
        key = self.normalize_name(
            key
        )

        with self._lock:
            section, storage_key = (
                self._storage_location(
                    category,
                    key,
                )
            )

            deleted = False

            if section == "likes":
                old_size = len(
                    self._data["likes"]
                )

                self._data["likes"] = [
                    value
                    for value in self._data[
                        "likes"
                    ]
                    if (
                        self.normalize_name(
                            value
                        )
                        != self.normalize_name(
                            key
                        )
                    )
                ]

                deleted = (
                    len(self._data["likes"])
                    < old_size
                )

            elif section in {
                "profile",
                "family",
                "personal",
            }:
                deleted = (
                    self._data[
                        section
                    ].pop(
                        storage_key,
                        None,
                    )
                    is not None
                )

            else:
                bucket = self._data[
                    "other"
                ].get(
                    section,
                    {},
                )

                deleted = (
                    bucket.pop(
                        storage_key,
                        None,
                    )
                    is not None
                )

                if not bucket:
                    self._data[
                        "other"
                    ].pop(
                        section,
                        None,
                    )

            if deleted:
                self._data["_meta"].pop(
                    self._meta_id(
                        category,
                        key,
                    ),
                    None,
                )
                self._data[
                    "updated_at"
                ] = self._now()
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
        Return natural, authoritative memory context for Realtime and AI.
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
            (
                "The following information is the user's "
                "authoritative permanent profile."
            ),
            (
                "Use it naturally when relevant. "
                "Do not claim that you know nothing about the user."
            ),
            (
                "Do not mention internal memory files, categories, "
                "keys, or storage systems."
            ),
            "",
            "User profile:",
        ]

        labels = {
            "name": "Name",
            "favorite_language": (
                "Favorite language"
            ),
            "wife_name": "Wife",
            "husband_name": "Husband",
            "daughter_name": "Daughter",
            "son_name": "Son",
            "mother_name": "Mother",
            "father_name": "Father",
            "sister_name": "Sister",
            "brother_name": "Brother",
            "son_in_law": "Son-in-law",
            "son_in_law_name": "Son-in-law",
            "daughter_in_law_name": (
                "Daughter-in-law"
            ),
        }

        likes = []

        for fact in facts:
            category = fact["category"]
            key = fact["key"]
            value = fact["value"]

            if category == "likes":
                likes.append(
                    value
                )
                continue

            label = labels.get(
                key,
                key.replace(
                    "_",
                    " ",
                ).title(),
            )

            lines.append(
                f"- {label}: {value}"
            )

        if likes:
            lines.append(
                "- Likes: "
                + ", ".join(
                    likes
                )
            )

        return "\n".join(lines)

    def diagnostics(self):
        with self._lock:
            return {
                "memory_file": str(
                    self.memory_file
                ),
                "version": MEMORY_VERSION,
                "fact_count": len(
                    self.list_facts()
                ),
                "facts": self.list_facts(),
                "structured": deepcopy(
                    self._data
                ),
            }

    def _storage_location(
        self,
        category,
        key,
    ):
        if category == "likes":
            return "likes", key

        if category == "family":
            return (
                "family",
                self.FAMILY_STORAGE_ALIASES.get(
                    key,
                    key,
                ),
            )

        if category == "preferences":
            if key == "favorite_language":
                return (
                    "profile",
                    "favorite_language",
                )

            return "personal", key

        if category == "profile":
            return "profile", key

        if category in {
            "personal",
            "general",
        }:
            return "personal", key

        return category, key

    @staticmethod
    def _meta_id(
        category,
        key,
    ):
        return (
            f"{category}.{key}"
        )

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
