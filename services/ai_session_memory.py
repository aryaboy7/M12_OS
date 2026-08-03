import json
import os
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_MAX_MESSAGES = 30
DEFAULT_MAX_CHARACTERS = 16000
MEMORY_VERSION = 1


class AISessionMemory:
    """
    Shared persistent conversation memory for M12 AI.

    Design goals:
        - One history shared by normal AI and Internet AI.
        - Works on macOS, Linux, Windows, M12, and Android.
        - Survives screen changes and application restarts.
        - Thread-safe for typed, voice, and streaming requests.
        - Uses atomic JSON writes to reduce corruption risk.
        - Keeps history bounded so prompts and storage do not grow forever.
    """

    VALID_ROLES = {"user", "assistant", "system"}
    VALID_ROUTES = {None, "normal", "internet"}

    def __init__(
        self,
        memory_file=None,
        max_messages=DEFAULT_MAX_MESSAGES,
        max_characters=DEFAULT_MAX_CHARACTERS,
    ):
        self.max_messages = max(2, int(max_messages))
        self.max_characters = max(1000, int(max_characters))
        self._lock = threading.RLock()

        if memory_file is None:
            self.memory_file = self.default_memory_file()
        else:
            self.memory_file = Path(memory_file).expanduser()

        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._empty_data()
        self.load()

    @classmethod
    def default_memory_file(cls):
        """
        Return a writable cross-platform memory-file path.

        Priority:
            1. M12_AI_DATA_DIR environment variable.
            2. Running Kivy application's user_data_dir.
            3. Android private application directory.
            4. Project data/ai directory for desktop development.
        """
        explicit_directory = os.getenv("M12_AI_DATA_DIR", "").strip()

        if explicit_directory:
            return Path(explicit_directory).expanduser() / "session_memory.json"

        kivy_directory = cls._kivy_user_data_dir()

        if kivy_directory is not None:
            return kivy_directory / "ai" / "session_memory.json"

        android_private = os.getenv("ANDROID_PRIVATE", "").strip()

        if android_private:
            return Path(android_private) / "ai" / "session_memory.json"

        return BASE_DIR / "data" / "ai" / "session_memory.json"

    @staticmethod
    def _kivy_user_data_dir():
        """
        Read Kivy's writable application directory when available.

        Import errors are intentionally ignored so this service can also
        be tested without loading the Kivy interface.
        """
        try:
            from kivy.app import App

            running_app = App.get_running_app()

            if running_app is None:
                return None

            user_data_dir = str(
                getattr(running_app, "user_data_dir", "")
            ).strip()

            if not user_data_dir:
                return None

            return Path(user_data_dir)

        except Exception:
            return None

    @staticmethod
    def _utc_timestamp():
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _empty_data(self):
        return {
            "version": MEMORY_VERSION,
            "updated_at": self._utc_timestamp(),
            "last_route": None,
            "messages": [],
        }

    def load(self):
        """
        Load memory from disk.

        A missing, malformed, or incompatible file does not stop M12.
        Invalid content is replaced with a clean in-memory structure.
        """
        with self._lock:
            if not self.memory_file.exists():
                self._data = self._empty_data()
                return

            try:
                with self.memory_file.open("r", encoding="utf-8") as file:
                    loaded = json.load(file)

                self._data = self._validate_data(loaded)
                self._trim_locked()

            except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
                print(
                    "AI session memory load error: "
                    f"{type(error).__name__}: {error}"
                )
                self._backup_damaged_file()
                self._data = self._empty_data()

    def _validate_data(self, loaded):
        if not isinstance(loaded, dict):
            return self._empty_data()

        messages = loaded.get("messages", [])
        clean_messages = []

        if isinstance(messages, list):
            for item in messages:
                clean_message = self._validate_message(item)

                if clean_message is not None:
                    clean_messages.append(clean_message)

        last_route = loaded.get("last_route")

        if last_route not in self.VALID_ROUTES:
            last_route = None

        return {
            "version": MEMORY_VERSION,
            "updated_at": str(
                loaded.get("updated_at", self._utc_timestamp())
            ),
            "last_route": last_route,
            "messages": clean_messages,
        }

    def _validate_message(self, item):
        if not isinstance(item, dict):
            return None

        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()

        if role not in self.VALID_ROLES or not content:
            return None

        route = item.get("route")

        if route not in self.VALID_ROUTES:
            route = None

        timestamp = str(item.get("timestamp", self._utc_timestamp()))

        result = {
            "role": role,
            "content": content,
            "timestamp": timestamp,
        }

        if route is not None:
            result["route"] = route

        return result

    def add_message(self, role, content, route=None):
        """
        Add one message and save it immediately.

        Returns True when a message was added.
        """
        clean_role = str(role).strip().lower()
        clean_content = str(content).strip()

        if clean_role not in self.VALID_ROLES or not clean_content:
            return False

        if route not in self.VALID_ROUTES:
            route = None

        message = {
            "role": clean_role,
            "content": clean_content,
            "timestamp": self._utc_timestamp(),
        }

        if route is not None:
            message["route"] = route

        with self._lock:
            self._data["messages"].append(message)

            if route is not None:
                self._data["last_route"] = route

            self._data["updated_at"] = self._utc_timestamp()
            self._trim_locked()
            self._save_locked()

        return True

    def add_user(self, content, route=None):
        return self.add_message("user", content, route)

    def add_assistant(self, content, route=None):
        return self.add_message("assistant", content, route)

    def add_system(self, content):
        return self.add_message("system", content)

    def set_last_route(self, route):
        if route not in self.VALID_ROUTES:
            raise ValueError("Route must be 'normal', 'internet', or None.")

        with self._lock:
            self._data["last_route"] = route
            self._data["updated_at"] = self._utc_timestamp()
            self._save_locked()

    def get_last_route(self):
        with self._lock:
            return self._data.get("last_route")

    def get_messages(self, limit=None, include_system=True):
        """Return a safe copy of recent messages."""
        with self._lock:
            messages = list(self._data.get("messages", []))

            if not include_system:
                messages = [
                    message
                    for message in messages
                    if message.get("role") != "system"
                ]

            if limit is not None:
                safe_limit = max(0, int(limit))
                messages = [] if safe_limit == 0 else messages[-safe_limit:]

            return deepcopy(messages)

    def get_openai_messages(self, limit=None, include_system=True):
        """
        Return OpenAI-compatible role/content dictionaries.

        Timestamps and internal route fields are intentionally omitted.
        """
        messages = self.get_messages(
            limit=limit,
            include_system=include_system,
        )

        return [
            {
                "role": message["role"],
                "content": message["content"],
            }
            for message in messages
        ]

    def get_history_text(self, limit=None, include_system=False):
        """Return a compact plain-text conversation transcript."""
        messages = self.get_messages(
            limit=limit,
            include_system=include_system,
        )

        labels = {
            "user": "User",
            "assistant": "M12 AI",
            "system": "System",
        }

        return "\n".join(
            f"{labels.get(message['role'], message['role'])}: "
            f"{message['content']}"
            for message in messages
        )

    def message_count(self):
        with self._lock:
            return len(self._data.get("messages", []))

    def clear(self):
        """Clear current session memory and persist the empty state."""
        with self._lock:
            self._data = self._empty_data()
            self._save_locked()

    def reload(self):
        self.load()

    def save(self):
        with self._lock:
            self._trim_locked()
            self._save_locked()

    def _trim_locked(self):
        messages = self._data.get("messages", [])

        if len(messages) > self.max_messages:
            messages = messages[-self.max_messages:]

        total_characters = sum(
            len(str(message.get("content", "")))
            for message in messages
        )

        while len(messages) > 2 and total_characters > self.max_characters:
            removed = messages.pop(0)
            total_characters -= len(str(removed.get("content", "")))

        self._data["messages"] = messages

    def _save_locked(self):
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)

        payload = json.dumps(
            self._data,
            ensure_ascii=False,
            indent=2,
        ) + "\n"

        temporary_path = None

        try:
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=self.memory_file.stem + "_",
                suffix=".tmp",
                dir=str(self.memory_file.parent),
            )

            temporary_path = Path(temporary_name)

            with os.fdopen(
                file_descriptor,
                "w",
                encoding="utf-8",
            ) as temporary_file:
                temporary_file.write(payload)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, self.memory_file)

        except OSError as error:
            print(
                "AI session memory save error: "
                f"{type(error).__name__}: {error}"
            )

            if temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    def _backup_damaged_file(self):
        if not self.memory_file.exists():
            return

        backup_name = (
            self.memory_file.name
            + ".damaged-"
            + datetime.now().strftime("%Y%m%d-%H%M%S")
        )

        backup_path = self.memory_file.parent / backup_name

        try:
            os.replace(self.memory_file, backup_path)
        except OSError:
            pass

    def diagnostics(self):
        """Return basic information useful during M12 testing."""
        with self._lock:
            return {
                "memory_file": str(self.memory_file),
                "message_count": len(self._data.get("messages", [])),
                "last_route": self._data.get("last_route"),
                "max_messages": self.max_messages,
                "max_characters": self.max_characters,
            }


_shared_memory = None
_shared_memory_lock = threading.Lock()


def get_ai_session_memory():
    """Return one shared AISessionMemory instance for the application."""
    global _shared_memory

    if _shared_memory is None:
        with _shared_memory_lock:
            if _shared_memory is None:
                _shared_memory = AISessionMemory()

    return _shared_memory
