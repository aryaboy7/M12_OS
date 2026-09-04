import json
import mimetypes
import os
import ssl
import tempfile
import uuid
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError

import certifi

from services.audd_key_manager import AudDKeyManager


class MusicRecognitionService:
    """
    Identifies music captured by M12.

    Audio capture and recognition providers are intentionally kept
    separate from the Music Recognition skill.
    """

    AUDD_ENDPOINT = "https://api.audd.io/"
    DEFAULT_AUDIO_PATH = (
        Path(tempfile.gettempdir())
        / "m12_music_recognition.wav"
    )

    def __init__(self):
        self.provider = "audd"

    def _api_token(self):
        """
        Return the AudD API token from the environment.

        The token is intentionally not stored in source code.
        """
        return AudDKeyManager.get_token()

    def recognize(self, audio_path=None):
        """
        Recognize a local audio file.

        Audio capture will be connected separately. Keeping capture
        separate lets the same recognition code work on Zorin and
        Android.
        """
        if not audio_path:
            audio_path = self.DEFAULT_AUDIO_PATH

        token = self._api_token()

        if not token:
            return {
                "success": False,
                "status": "not_configured",
                "title": "",
                "artist": "",
                "album": "",
                "provider": self.provider,
            }

        path = Path(audio_path)

        if not path.is_file():
            return {
                "success": False,
                "status": "audio_file_not_found",
                "title": "",
                "artist": "",
                "album": "",
                "provider": self.provider,
            }

        try:
            response = self._send_file(
                path=path,
                token=token,
            )
        except HTTPError as error:
            return {
                "success": False,
                "status": "http_error",
                "error": str(error),
                "title": "",
                "artist": "",
                "album": "",
                "provider": self.provider,
            }
        except URLError as error:
            return {
                "success": False,
                "status": "network_error",
                "error": str(error),
                "title": "",
                "artist": "",
                "album": "",
                "provider": self.provider,
            }
        except Exception as error:
            return {
                "success": False,
                "status": "error",
                "error": (
                    f"{type(error).__name__}: {error}"
                ),
                "title": "",
                "artist": "",
                "album": "",
                "provider": self.provider,
            }

        if response.get("status") != "success":
            return {
                "success": False,
                "status": "provider_error",
                "error": response.get("error"),
                "title": "",
                "artist": "",
                "album": "",
                "provider": self.provider,
            }

        result = response.get("result")

        if not isinstance(result, dict):
            return {
                "success": False,
                "status": "not_recognized",
                "title": "",
                "artist": "",
                "album": "",
                "provider": self.provider,
            }

        return {
            "success": True,
            "status": "recognized",
            "title": str(
                result.get("title", "")
            ).strip(),
            "artist": str(
                result.get("artist", "")
            ).strip(),
            "album": str(
                result.get("album", "")
            ).strip(),
            "provider": self.provider,
        }

    def _send_file(self, path, token):
        """
        Upload an audio file to AudD using multipart/form-data.
        """
        boundary = (
            "----M12MusicRecognition"
            + uuid.uuid4().hex
        )

        boundary_bytes = boundary.encode("ascii")
        body = bytearray()

        def add_text(name, value):
            body.extend(b"--" + boundary_bytes + b"\r\n")
            body.extend(
                (
                    f'Content-Disposition: form-data; '
                    f'name="{name}"\r\n\r\n'
                ).encode("utf-8")
            )
            body.extend(
                str(value).encode("utf-8")
            )
            body.extend(b"\r\n")

        add_text("api_token", token)

        mime_type = (
            mimetypes.guess_type(path.name)[0]
            or "application/octet-stream"
        )

        body.extend(
            b"--" + boundary_bytes + b"\r\n"
        )
        body.extend(
            (
                'Content-Disposition: form-data; '
                f'name="file"; filename="{path.name}"\r\n'
            ).encode("utf-8")
        )
        body.extend(
            (
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8")
        )

        with path.open("rb") as audio_file:
            body.extend(audio_file.read())

        body.extend(b"\r\n")
        body.extend(
            b"--" + boundary_bytes + b"--\r\n"
        )

        req = request.Request(
            self.AUDD_ENDPOINT,
            data=bytes(body),
            headers={
                "Content-Type": (
                    "multipart/form-data; "
                    f"boundary={boundary}"
                ),
                "User-Agent": "M12-OS/0.5.3",
            },
            method="POST",
        )

        ssl_context = ssl.create_default_context(
            cafile=certifi.where()
        )

        with request.urlopen(
            req,
            timeout=30,
            context=ssl_context,
        ) as response:
            raw = response.read().decode(
                "utf-8",
                errors="replace",
            )

        return json.loads(raw)