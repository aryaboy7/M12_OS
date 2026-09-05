import json
import os

from services.api_key_manager import APIKeyManager


CREDENTIALS_FILENAME = "spotify_credentials.json"
CREDENTIALS_FIELD = "spotify_client_id"


class SpotifyClientManager:
    """
    Shared M12 Spotify Client ID storage.

    The Spotify Client ID is not a secret, but M12 stores it in the same
    private application configuration area as other service credentials.

    Priority:
    1. Client ID saved from M12 Security Key Setup.
    2. SPOTIFY_CLIENT_ID environment variable as fallback.
    """

    @staticmethod
    def normalize_client_id(value):
        return str(value or "").strip()

    @classmethod
    def private_directory(cls):
        return APIKeyManager.private_directory()

    @classmethod
    def credentials_file(cls):
        return (
            cls.private_directory()
            / CREDENTIALS_FILENAME
        )

    @classmethod
    def load_private_client_id(cls):
        path = cls.credentials_file()

        if not path.exists():
            return ""

        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

            if not isinstance(data, dict):
                return ""

            return cls.normalize_client_id(
                data.get(
                    CREDENTIALS_FIELD,
                    "",
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ):
            return ""

    @classmethod
    def get_client_id(cls):
        private_value = (
            cls.load_private_client_id()
        )

        if private_value:
            return private_value

        return cls.normalize_client_id(
            os.getenv(
                "SPOTIFY_CLIENT_ID",
                "",
            )
        )

    @classmethod
    def has_client_id(cls):
        return bool(
            cls.get_client_id()
        )

    @classmethod
    def client_id_source(cls):
        if cls.load_private_client_id():
            return "M12 private storage"

        if cls.normalize_client_id(
            os.getenv(
                "SPOTIFY_CLIENT_ID",
                "",
            )
        ):
            return "SPOTIFY_CLIENT_ID environment"

        return "Not configured"

    @classmethod
    def save_client_id(
        cls,
        value,
    ):
        client_id = (
            cls.normalize_client_id(
                value
            )
        )

        if not client_id:
            raise ValueError(
                "Spotify Client ID cannot be empty."
            )

        path = cls.credentials_file()
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = path.with_suffix(
            ".tmp"
        )

        data = {
            CREDENTIALS_FIELD: client_id,
        }

        with temporary.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")

        try:
            os.chmod(
                temporary,
                0o600,
            )
        except OSError:
            pass

        os.replace(
            temporary,
            path,
        )

        try:
            os.chmod(
                path,
                0o600,
            )
        except OSError:
            pass

        return True

    @classmethod
    def delete_client_id(cls):
        path = cls.credentials_file()

        try:
            path.unlink(
                missing_ok=True
            )
            return True

        except OSError as error:
            raise RuntimeError(
                "Unable to remove the saved "
                "Spotify Client ID: "
                f"{type(error).__name__}: {error}"
            ) from error