import json
from pathlib import Path

from kivy.utils import platform


BASE_DIR = Path(__file__).resolve().parent.parent
LEGACY_CONFIG_DIR = BASE_DIR / "config"
LEGACY_SETTINGS_FILE = LEGACY_CONFIG_DIR / "settings.json"


DEFAULT_SETTINGS = {
    "city": "Brooklyn, NY",
    "temperature_unit": "F",
    "theme": "dark",
    "auto_update": True,
    "update_channel": "stable",
    "start_screen": "home",
    "last_update_check": "",

    "last_temperature": "--",
    "last_condition": "",
    "last_humidity": "",
    "last_wind": "",
    "last_advice": "",

    # User AI preferences. These belong in persistent user storage,
    # not in files that are shipped as part of the APK.
    "speaker_echo_protection": True,
    "voice_language": "en",
}


def _android_private_settings_file():
    """Return a settings path inside Android private app storage."""
    # Preferred python-for-android helper.
    try:
        from android.storage import app_storage_path

        root = Path(app_storage_path())
        root.mkdir(parents=True, exist_ok=True)
        return root / "settings.json"
    except Exception:
        pass

    # Reliable fallback through Android Context.
    try:
        from jnius import autoclass

        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )
        activity = PythonActivity.mActivity
        files_dir = activity.getFilesDir()
        root = Path(str(files_dir.getAbsolutePath()))
        root.mkdir(parents=True, exist_ok=True)
        return root / "settings.json"
    except Exception:
        pass

    # Last-resort fallback. This preserves old behavior if Android private
    # storage is unavailable for an unexpected reason.
    LEGACY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return LEGACY_SETTINGS_FILE


def get_settings_file():
    if platform == "android":
        return _android_private_settings_file()

    LEGACY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return LEGACY_SETTINGS_FILE


SETTINGS_FILE = get_settings_file()


class ConfigManager:
    def __init__(
        self,
        path=None,
    ):
        self.path = Path(
            path if path is not None else SETTINGS_FILE
        )
        self.data = DEFAULT_SETTINGS.copy()
        self.load()

    def _load_json_file(self, path):
        try:
            if not path.exists():
                return None

            loaded = json.loads(
                path.read_text(encoding="utf-8")
            )

            if isinstance(loaded, dict):
                return loaded
        except Exception:
            pass

        return None

    def _migrate_legacy_settings(self):
        """
        Seed a new Android private settings file from older source-tree
        settings when they are still available.

        This runs only when the new private settings file does not yet exist.
        """
        if platform != "android":
            return False

        migrated = False

        legacy_settings = self._load_json_file(
            LEGACY_SETTINGS_FILE
        )

        if legacy_settings:
            self.data.update(legacy_settings)
            migrated = True

        # Older M12 builds stored these two AI preferences in ai_settings.json.
        legacy_ai_file = LEGACY_CONFIG_DIR / "ai_settings.json"
        legacy_ai = self._load_json_file(legacy_ai_file)

        if legacy_ai:
            for key in (
                "speaker_echo_protection",
                "voice_language",
            ):
                if key in legacy_ai:
                    self.data[key] = legacy_ai[key]
                    migrated = True

        if migrated:
            self.save()

        return migrated

    def load(self):
        if not self.path.exists():
            if not self._migrate_legacy_settings():
                self.save()
            return self.data

        try:
            loaded = json.loads(
                self.path.read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(loaded, dict):
                self.data.update(loaded)

        except Exception:
            self.data = DEFAULT_SETTINGS.copy()
            self.save()

        return self.data

    def save(self):
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_file = self.path.with_suffix(
            self.path.suffix + ".tmp"
        )

        temporary_file.write_text(
            json.dumps(
                self.data,
                indent=4,
                ensure_ascii=False,
            ) + "\n",
            encoding="utf-8",
        )

        temporary_file.replace(self.path)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def all(self):
        return self.data.copy()