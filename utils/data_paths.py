from __future__ import annotations

import shutil
from pathlib import Path

from kivy.utils import platform


BASE_DIR = Path(__file__).resolve().parent.parent
PACKAGED_DATA_ROOT = BASE_DIR / "data"

# User-owned folders that must survive Android APK upgrades.
PERSISTENT_FOLDERS = (
    "notes",
    "events",
    "alarms",
    "memory",
    "music",
    "drawings",
    "bluetooth",
    "ai",
    "backups",
)


def _android_files_root() -> Path:
    """
    Return Android's persistent private files directory.

    Typical result:
        /data/user/0/com.m12os.m12os/files

    This directory survives `adb install -r` APK upgrades.
    """
    from android.storage import app_storage_path

    return Path(app_storage_path()).resolve()


def user_data_root() -> Path:
    """
    Writable M12 user-data root.

    Desktop:
        <project>/data

    Android:
        <private app files>/user_data
    """
    if platform == "android":
        return _android_files_root() / "user_data"

    return PACKAGED_DATA_ROOT


def packaged_data_path(*parts: str) -> Path:
    """
    Path to read-only/packaged application assets such as reminder sounds.
    """
    return PACKAGED_DATA_ROOT.joinpath(*parts)


def data_path(*parts: str) -> Path:
    """
    Path to writable user data.

    Calling this also performs a safe one-way Android migration from the
    old packaged data location into the persistent user-data location.
    """
    root = ensure_persistent_data()
    return root.joinpath(*parts)


def _copy_missing_tree(source: Path, destination: Path) -> None:
    """
    Merge source into destination without overwriting files that already
    exist in the new persistent location.
    """
    if not source.exists():
        return

    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)
        return

    destination.mkdir(parents=True, exist_ok=True)

    for item in source.rglob("*"):
        relative = item.relative_to(source)
        target = destination / relative

        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)

        # Never replace a newer/persistent file during migration.
        if not target.exists():
            shutil.copy2(item, target)


def ensure_persistent_data() -> Path:
    """
    Create the writable data root and, on Android, safely migrate legacy
    user data from files/app/data/* to files/user_data/*.

    Migration is intentionally non-destructive:
      - old files are NOT deleted;
      - existing files in user_data are NOT overwritten;
      - the operation is safe to run repeatedly.
    """
    root = user_data_root()
    root.mkdir(parents=True, exist_ok=True)

    if platform == "android":
        for folder_name in PERSISTENT_FOLDERS:
            legacy = PACKAGED_DATA_ROOT / folder_name
            persistent = root / folder_name

            _copy_missing_tree(
                legacy,
                persistent,
            )

    for folder_name in PERSISTENT_FOLDERS:
        (root / folder_name).mkdir(
            parents=True,
            exist_ok=True,
        )

    return root


# Convenience paths used by many M12 modules.
NOTES_DIR = data_path("notes")
EVENTS_DIR = data_path("events")
EVENTS_FILE = EVENTS_DIR / "events.json"

ALARMS_DIR = data_path("alarms")
ALARMS_FILE = ALARMS_DIR / "alarms.json"

MEMORY_DIR = data_path("memory")

MUSIC_DIR = data_path("music")
FAVORITES_FILE = MUSIC_DIR / "favorites.json"
MUSIC_STATUS_FILE = MUSIC_DIR / "player_status.json"

DRAWINGS_DIR = data_path("drawings")

BLUETOOTH_DIR = data_path("bluetooth")
BT_DEFAULT_FILE = BLUETOOTH_DIR / "default_speaker.json"

AI_DIR = data_path("ai")
AI_CONVERSATION_FILE = AI_DIR / "conversation_history.txt"
AI_SESSION_MEMORY_FILE = AI_DIR / "session_memory.json"

BACKUPS_DIR = data_path("backups")

# Sounds ship with the application and do not need persistence.
SOUNDS_DIR = packaged_data_path("sounds")
REMINDER_SOUND_FILE = SOUNDS_DIR / "reminder.wav"
