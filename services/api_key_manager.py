import json
import os
from pathlib import Path

from kivy.app import App
from kivy.utils import platform as kivy_platform


CREDENTIALS_FILENAME = "ai_credentials.json"
CREDENTIALS_FIELD = "openai_api_key"


class APIKeyManager:
    """
    Shared M12 OpenAI credential storage.

    Android:
        The key is stored in M12's private application data directory.
        It is not stored in config/, Git, or the APK source tree.

    Desktop:
        OPENAI_API_KEY remains the preferred source.
        A private per-user file is also supported as a fallback.
    """

    @staticmethod
    def private_directory():
        app = App.get_running_app()

        if app is not None:
            user_data_dir = str(
                getattr(
                    app,
                    "user_data_dir",
                    "",
                )
                or ""
            ).strip()

            if user_data_dir:
                path = Path(user_data_dir)
                path.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                return path

        if kivy_platform == "android":
            try:
                from jnius import autoclass

                PythonActivity = autoclass(
                    "org.kivy.android.PythonActivity"
                )
                activity = PythonActivity.mActivity
                path = Path(
                    str(
                        activity.getFilesDir().getAbsolutePath()
                    )
                )
                path.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                return path

            except Exception as error:
                raise RuntimeError(
                    "Unable to locate M12 private Android storage: "
                    f"{type(error).__name__}: {error}"
                ) from error

        path = Path.home() / ".m12_os"
        path.mkdir(
            parents=True,
            exist_ok=True,
        )
        return path

    @classmethod
    def credentials_file(cls):
        return (
            cls.private_directory()
            / CREDENTIALS_FILENAME
        )

    @staticmethod
    def normalize_key(value):
        return str(value or "").strip()

    @classmethod
    def load_private_key(cls):
        path = cls.credentials_file()

        if not path.exists():
            return ""

        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

            if not isinstance(
                data,
                dict,
            ):
                return ""

            return cls.normalize_key(
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
    def get_api_key(cls):
        """
        Return the active OpenAI key without reading config/ai_settings.json.
        """
        private_key = cls.load_private_key()

        if kivy_platform == "android":
            if private_key:
                return private_key

            # Environment fallback is useful for developer builds, but M12
            # never writes an environment key into the APK itself.
            return cls.normalize_key(
                os.getenv(
                    "OPENAI_API_KEY",
                    "",
                )
            )

        environment_key = cls.normalize_key(
            os.getenv(
                "OPENAI_API_KEY",
                "",
            )
        )

        return environment_key or private_key

    @classmethod
    def key_source(cls):
        private_key = cls.load_private_key()

        if (
            kivy_platform == "android"
            and private_key
        ):
            return "Android private storage"

        environment_key = cls.normalize_key(
            os.getenv(
                "OPENAI_API_KEY",
                "",
            )
        )

        if environment_key:
            return "OPENAI_API_KEY environment"

        if private_key:
            return "M12 private storage"

        return "Not configured"

    @classmethod
    def has_key(cls):
        return bool(
            cls.get_api_key()
        )

    @classmethod
    def save_api_key(cls, value):
        key = cls.normalize_key(value)

        if not key:
            raise ValueError(
                "OpenAI API key cannot be empty."
            )

        path = cls.credentials_file()
        temporary = path.with_suffix(
            ".tmp"
        )

        data = {
            CREDENTIALS_FIELD: key,
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
    def delete_api_key(cls):
        path = cls.credentials_file()

        try:
            path.unlink(
                missing_ok=True
            )
            return True

        except OSError as error:
            raise RuntimeError(
                "Unable to remove the saved OpenAI API key: "
                f"{type(error).__name__}: {error}"
            ) from error