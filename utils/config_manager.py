import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = CONFIG_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "city": "Brooklyn, NY",
    "temperature_unit": "F",
    "theme": "dark",
    "auto_update": True,
    "update_channel": "stable",
    "start_screen": "home",
    "last_update_check": ""
}


class ConfigManager:
    def __init__(self, path=SETTINGS_FILE):
        self.path = Path(path)
        self.data = DEFAULT_SETTINGS.copy()
        self.load()

    def load(self):
        if not self.path.exists():
            self.save()
            return self.data

        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except Exception:
            self.data = DEFAULT_SETTINGS.copy()
            self.save()

        return self.data

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=4), encoding="utf-8")

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def all(self):
        return self.data.copy()
