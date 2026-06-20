import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

STORAGE_ROOTS_FILE = CONFIG_DIR / "storage_roots.json"

DEFAULT_STORAGE_ROOTS = {
    "internal_root": "/storage/emulated/0",
    "external_root": "/storage/0907-1477",
}


def load_storage_roots():
    data = DEFAULT_STORAGE_ROOTS.copy()

    try:
        if STORAGE_ROOTS_FILE.exists():
            saved = json.loads(
                STORAGE_ROOTS_FILE.read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(saved, dict):
                data.update(saved)

    except Exception:
        pass

    return data


def save_storage_roots(internal_root, external_root):
    data = {
        "internal_root": (
            internal_root.strip()
            or DEFAULT_STORAGE_ROOTS["internal_root"]
        ),
        "external_root": (
            external_root.strip()
            or DEFAULT_STORAGE_ROOTS["external_root"]
        ),
    }

    STORAGE_ROOTS_FILE.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )

    return data