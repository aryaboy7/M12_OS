import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

from config.version import VERSION, UPDATE_INFO_URL
from utils.logger import log


BASE_DIR = Path(__file__).resolve().parent.parent
UPDATES_DIR = BASE_DIR / "updates"
BACKUPS_DIR = BASE_DIR / "backups"

UPDATES_DIR.mkdir(exist_ok=True)
BACKUPS_DIR.mkdir(exist_ok=True)

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
SKIP_NAMES = {
    ".DS_Store",
    "requirements.txt",   # Android can throw permission error here
}


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


class Updater:
    def __init__(self, config=None, update_info_url=UPDATE_INFO_URL):
        self.config = config
        self.update_info_url = update_info_url

    def check(self):
        try:
            with urllib.request.urlopen(self.update_info_url, timeout=15) as response:
                raw = response.read().decode("utf-8")
                info = json.loads(raw)

            remote_version = info.get("version", "0.0.0")
            info["local_version"] = VERSION
            info["update_available"] = is_newer(remote_version, VERSION)

            if self.config:
                self.config.set(
                    "last_update_check",
                    datetime.now().isoformat(timespec="seconds")
                )

            log.info(f"Updater check OK: local={VERSION}, remote={remote_version}")
            return info

        except Exception as e:
            log.error(f"Updater check failed: {e}")
            return {
                "error": str(e),
                "local_version": VERSION,
                "update_available": False
            }

    def download(self, file_url):
        if not file_url:
            return {"ok": False, "error": "No file_url in update.json"}

        try:
            filename = file_url.rstrip("/").split("/")[-1]

            if not filename.lower().endswith(".zip"):
                filename += ".zip"

            target = UPDATES_DIR / filename

            if target.exists():
                target.unlink()

            urllib.request.urlretrieve(file_url, target)

            log.info(f"Update downloaded: {target}")

            return {
                "ok": True,
                "path": str(target)
            }

        except Exception as e:
            log.error(f"Updater download failed: {e}")
            return {
                "ok": False,
                "error": str(e)
            }

    def latest_downloaded_zip(self):
        zips = sorted(
            UPDATES_DIR.glob("*.zip"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        return zips[0] if zips else None

    def _should_skip_file(self, rel_path, src):
        rel = rel_path.as_posix()

        if rel_path.parts and rel_path.parts[0] in PRESERVE_NAMES:
            return True

        if rel in PRESERVE_FILES:
            return True

        if src.name in SKIP_NAMES:
            return True

        if src.suffix.lower() in SKIP_SUFFIXES:
            return True

        if "__MACOSX" in rel_path.parts:
            return True

        if ".venv" in rel_path.parts:
            return True

        return False

    def make_backup(self):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUPS_DIR / f"M12_OS_backup_{VERSION}_{stamp}.zip"

        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in BASE_DIR.rglob("*"):
                if not path.is_file():
                    continue

                rel_path = path.relative_to(BASE_DIR)

                if self._should_skip_file(rel_path, path):
                    continue

                zf.write(path, rel_path)

        log.info(f"Backup created: {backup_path}")
        return backup_path

    def _find_update_root(self, extracted_dir):
        extracted_dir = Path(extracted_dir)

        possible_roots = [
            extracted_dir / "M12_OS",
            extracted_dir / "M12_05",
            extracted_dir / "M12_OS-main",
            extracted_dir / "M12_05-main",
        ]

        for root in possible_roots:
            if (root / "main.py").exists():
                return root

        candidates = list(extracted_dir.rglob("main.py"))

        for main_file in candidates:
            parent = main_file.parent

            if (
                (parent / "screens").exists()
                and
                (parent / "config").exists()
                and
                (parent / "utils").exists()
            ):
                return parent

        if candidates:
            return candidates[0].parent

        raise RuntimeError("Update ZIP does not contain main.py")

    def install_zip(self, zip_path=None):
        try:
            source_zip = Path(zip_path) if zip_path else self.latest_downloaded_zip()

            if not source_zip or not source_zip.exists():
                return {
                    "ok": False,
                    "error": "No downloaded ZIP found."
                }

            backup_path = self.make_backup()

            with tempfile.TemporaryDirectory(prefix="m12_update_") as tmp:
                tmp_path = Path(tmp)

                with zipfile.ZipFile(source_zip, "r") as zf:
                    zf.extractall(tmp_path)

                update_root = self._find_update_root(tmp_path)

                copied = 0
                skipped = 0

                for src in update_root.rglob("*"):
                    if not src.is_file():
                        continue

                    rel_path = src.relative_to(update_root)

                    if self._should_skip_file(rel_path, src):
                        skipped += 1
                        continue

                    dst = BASE_DIR / rel_path

                    try:
                        dst.parent.mkdir(parents=True, exist_ok=True)

                        if dst.exists():
                            try:
                                dst.unlink()
                            except Exception:
                                pass

                        shutil.copy2(src, dst)
                        copied += 1

                    except PermissionError as e:
                        skipped += 1
                        log.error(f"Permission denied copying {rel_path}: {e}")
                        continue

            log.info(
                f"Update installed: {source_zip} files={copied} skipped={skipped}"
            )

            return {
                "ok": True,
                "zip": str(source_zip),
                "backup": str(backup_path),
                "files_copied": copied,
                "files_skipped": skipped,
                "message": "Update installed. Restart M12 OS."
            }

        except Exception as e:
            log.error(f"Install failed: {e}")
            return {
                "ok": False,
                "error": str(e)
            }

    def restart_app(self):
        python = os.sys.executable
        args = [python] + os.sys.argv

        log.info("Restarting M12 OS")
        os.execv(python, args)