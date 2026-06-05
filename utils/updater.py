import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

from config.version import VERSION, UPDATE_INFO_URL, ZIP_URL
from utils.logger import log

BASE_DIR = Path(__file__).resolve().parent.parent
UPDATES_DIR = BASE_DIR / "updates"
BACKUPS_DIR = BASE_DIR / "backups"
UPDATES_DIR.mkdir(exist_ok=True)
BACKUPS_DIR.mkdir(exist_ok=True)

# These folders/files are preserved during upgrade.
# User data and settings must not be erased by an update.
PRESERVE_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "data",
    "logs",
    "updates",
    "backups",
}
PRESERVE_FILES = {
    "config/settings.json",
}
SKIP_SUFFIXES = {".pyc", ".pyo"}
SKIP_NAMES = {".DS_Store"}


def parse_version(value):
    parts = []
    for part in str(value).strip().split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def is_newer(remote_version, local_version=VERSION):
    return parse_version(remote_version) > parse_version(local_version)


def _rel(path):
    return path.relative_to(BASE_DIR).as_posix()


def _should_skip(path):
    rel = _rel(path) if path.is_relative_to(BASE_DIR) else path.name
    parts = set(Path(rel).parts)
    if parts & PRESERVE_NAMES:
        return True
    if rel in PRESERVE_FILES:
        return True
    if path.name in SKIP_NAMES:
        return True
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    return False


class Updater:
    def __init__(self, config=None, update_info_url=UPDATE_INFO_URL):
        self.config = config
        self.update_info_url = update_info_url

    def check(self):
        try:
            with urllib.request.urlopen(self.update_info_url, timeout=10) as response:
                raw = response.read().decode("utf-8")
                info = json.loads(raw)

            remote_version = info.get("version", "0.0.0")
            info["local_version"] = VERSION
            info["update_available"] = is_newer(remote_version, VERSION)

            if self.config:
                self.config.set("last_update_check", datetime.now().isoformat(timespec="seconds"))

            log.info(f"Updater check OK: local={VERSION}, remote={remote_version}")
            return info

        except Exception as e:
            log.error(f"Updater check failed: {e}")
            return {
                "error": str(e),
                "local_version": VERSION,
                "update_available": False
            }

    def download(self, url=None):
        file_url = url or ZIP_URL
        try:
            filename = file_url.rstrip("/").split("/")[-1] or "M12_05_update.zip"
            if not filename.lower().endswith(".zip"):
                filename += ".zip"

            target = UPDATES_DIR / filename
            urllib.request.urlretrieve(file_url, target)
            log.info(f"Updater downloaded: {target}")

            return {"ok": True, "path": str(target)}

        except Exception as e:
            log.error(f"Updater download failed: {e}")
            return {"ok": False, "error": str(e)}

    def latest_downloaded_zip(self):
        zips = sorted(UPDATES_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        return zips[0] if zips else None

    def make_backup(self):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUPS_DIR / f"M12_05_backup_{VERSION}_{stamp}.zip"

        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in BASE_DIR.rglob("*"):
                if not path.is_file():
                    continue
                if _should_skip(path):
                    continue
                zf.write(path, path.relative_to(BASE_DIR))

        log.info(f"Backup created: {backup_path}")
        return backup_path

    def _find_update_root(self, extracted_dir):
        extracted_dir = Path(extracted_dir)

        # Best case: ZIP has M12_05/main.py
        direct = extracted_dir / "M12_05" / "main.py"
        if direct.exists():
            return direct.parent

        # GitHub main.zip usually has repo-main/main.py
        candidates = list(extracted_dir.rglob("main.py"))
        for main_file in candidates:
            parent = main_file.parent
            if (parent / "screens").exists() and (parent / "config").exists():
                return parent

        if candidates:
            return candidates[0].parent

        raise RuntimeError("Update ZIP does not contain main.py")

    def install_zip(self, zip_path=None):
        try:
            source_zip = Path(zip_path) if zip_path else self.latest_downloaded_zip()
            if not source_zip or not source_zip.exists():
                return {"ok": False, "error": "No downloaded update ZIP found."}

            backup_path = self.make_backup()

            with tempfile.TemporaryDirectory(prefix="m12_update_") as tmp:
                tmp_path = Path(tmp)
                with zipfile.ZipFile(source_zip, "r") as zf:
                    zf.extractall(tmp_path)

                update_root = self._find_update_root(tmp_path)

                copied = 0
                for src in update_root.rglob("*"):
                    if not src.is_file():
                        continue

                    rel = src.relative_to(update_root).as_posix()
                    rel_path = Path(rel)

                    if rel_path.parts and rel_path.parts[0] in PRESERVE_NAMES:
                        continue
                    if rel in PRESERVE_FILES:
                        continue
                    if src.name in SKIP_NAMES or src.suffix.lower() in SKIP_SUFFIXES:
                        continue

                    dst = BASE_DIR / rel_path
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    copied += 1

            log.info(f"Update installed from {source_zip}, files copied={copied}")
            return {
                "ok": True,
                "zip": str(source_zip),
                "backup": str(backup_path),
                "files_copied": copied,
                "message": "Update installed. Restart M12 OS now."
            }

        except Exception as e:
            log.error(f"Install update failed: {e}")
            return {"ok": False, "error": str(e)}

    def restart_app(self):
        # Works on normal desktop Python/Kivy. If it fails, user can close/open manually.
        python = os.sys.executable
        args = [python] + os.sys.argv
        log.info("Restarting M12 OS")
        os.execv(python, args)
