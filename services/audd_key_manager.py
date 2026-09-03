import json
import os
from pathlib import Path

from kivy.utils import platform as kivy_platform

from services.api_key_manager import APIKeyManager


CREDENTIALS_FILENAME = "audd_credentials.json"
CREDENTIALS_FIELD = "audd_api_token"


class AudDKeyManager:
    """
    Shared M12 AudD credential storage.

    Android:
        The AudD key is stored in M12's private application data directory.
        It is not stored in config/, Git, or the APK source tree.

    Desktop:
        A key explicitly saved in M12 Settings has priority.
        AUDD_API_TOKEN is supported as a fallback.
    """

    @staticmethod
    def normalize_key(value):
        return str(value or "").strip()

    @classmethod
    def private_directory(cls):
        return APIKeyManager.private_directory()

    @classmethod
    def credentials_file(cls):
        return cls.private_directory() / CREDENTIALS_FILENAME

    @classmethod
    def load_private_token(cls):
        path = cls.credentials_file()

        if not path.exists():
            return ""

        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, dict):
                return ""

            return cls.normalize_key(
                data.get(CREDENTIALS_FIELD, "")
            )

        except (OSError, json.JSONDecodeError):
            return ""

    @classmethod
    def get_token(cls):
        """
        Return the active AudD API token.

        Priority on every platform:
        1. Key explicitly saved in M12 Settings/private storage.
        2. AUDD_API_TOKEN environment variable as fallback.
        """
        private_token = cls.load_private_token()

        if private_token:
            return private_token

        return cls.normalize_key(
            os.getenv("AUDD_API_TOKEN", "")
        )

    @classmethod
    def key_source(cls):
        private_token = cls.load_private_token()

        if private_token:
            if kivy_platform == "android":
                return "Android private storage"
            return "M12 private storage"

        environment_token = cls.normalize_key(
            os.getenv("AUDD_API_TOKEN", "")
        )

        if environment_token:
            return "AUDD_API_TOKEN environment"

        return "Not configured"

    @classmethod
    def has_key(cls):
        return bool(cls.get_token())

    @classmethod
    def save_token(cls, value):
        token = cls.normalize_key(value)

        if not token:
            raise ValueError(
                "AudD API key cannot be empty."
            )

        path = cls.credentials_file()
        temporary = path.with_suffix(".tmp")

        data = {
            CREDENTIALS_FIELD: token,
        }

        with temporary.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")

        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass

        os.replace(temporary, path)

        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

        return True

    @classmethod
    def delete_token(cls):
        path = cls.credentials_file()

        try:
            path.unlink(missing_ok=True)
            return True

        except OSError as error:
            raise RuntimeError(
                "Unable to remove the saved AudD API key: "
                f"{type(error).__name__}: {error}"
            ) from error