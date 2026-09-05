import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kivy.utils import platform as kivy_platform

from services.api_key_manager import APIKeyManager
from services.spotify_client_manager import SpotifyClientManager
from utils.logger import log


AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
PROFILE_URL = "https://api.spotify.com/v1/me"

REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 8888
REDIRECT_PATH = "/callback"
REDIRECT_URI = (
    f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}"
)

TOKEN_FILENAME = "spotify_authorization.json"

SCOPES = (
    "user-read-private",
    "user-read-playback-state",
    "user-modify-playback-state",
)


class SpotifyAuthService:
    """
    Automatic Spotify authorization for M12 using OAuth PKCE.

    First run:
        M12 opens Spotify authorization automatically.
        After approval, tokens are saved in private M12 storage.

    Later runs:
        M12 silently reuses the access token or refreshes it.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._worker = None
        self._authorization_in_progress = False

    @classmethod
    def token_file(cls):
        return APIKeyManager.private_directory() / TOKEN_FILENAME

    @staticmethod
    def _text(value):
        return str(value or "").strip()

    @staticmethod
    def _now():
        return int(time.time())

    @classmethod
    def load_tokens(cls):
        path = cls.token_file()

        if not path.exists():
            return {}

        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)

            return data if isinstance(data, dict) else {}

        except (OSError, json.JSONDecodeError) as error:
            log.error(
                "Spotify auth read failed: "
                f"{type(error).__name__}: {error}"
            )
            return {}

    @classmethod
    def save_tokens(cls, response, previous=None):
        if not isinstance(response, dict):
            raise RuntimeError("Spotify token response is invalid.")

        previous = previous if isinstance(previous, dict) else {}

        access_token = cls._text(response.get("access_token"))
        if not access_token:
            raise RuntimeError("Spotify returned no access token.")

        refresh_token = (
            cls._text(response.get("refresh_token"))
            or cls._text(previous.get("refresh_token"))
        )

        try:
            expires_in = int(response.get("expires_in", 3600))
        except (TypeError, ValueError):
            expires_in = 3600

        expires_in = max(60, expires_in)

        data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": (
                cls._text(response.get("token_type"))
                or cls._text(previous.get("token_type"))
                or "Bearer"
            ),
            "scope": (
                cls._text(response.get("scope"))
                or cls._text(previous.get("scope"))
                or " ".join(SCOPES)
            ),
            "expires_at": cls._now() + expires_in,
            "updated_at": cls._now(),
        }

        path = cls.token_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")

        with temporary.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
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

        return data

    @classmethod
    def token_is_valid(cls, data=None):
        data = data if isinstance(data, dict) else cls.load_tokens()

        access_token = cls._text(data.get("access_token"))

        try:
            expires_at = int(data.get("expires_at", 0))
        except (TypeError, ValueError):
            expires_at = 0

        return bool(
            access_token
            and expires_at > cls._now() + 60
        )

    @staticmethod
    def _post_form(url, fields):
        payload = urllib.parse.urlencode(fields).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()

        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Spotify HTTP {error.code}: {details}"
            ) from error

        except urllib.error.URLError as error:
            raise RuntimeError(
                f"Spotify network error: {error.reason}"
            ) from error

        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "Spotify returned invalid JSON."
            ) from error

        if not isinstance(data, dict):
            raise RuntimeError("Spotify returned an invalid response.")

        return data

    @staticmethod
    def _get_json(url, access_token):
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()

        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Spotify API HTTP {error.code}: {details}"
            ) from error

        except urllib.error.URLError as error:
            raise RuntimeError(
                f"Spotify API network error: {error.reason}"
            ) from error

        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "Spotify API returned invalid JSON."
            ) from error

        if not isinstance(data, dict):
            raise RuntimeError(
                "Spotify API returned an invalid response."
            )

        return data

    def refresh_access_token(self):
        client_id = SpotifyClientManager.get_client_id()

        if not client_id:
            raise RuntimeError("Spotify Client ID is not configured.")

        previous = self.load_tokens()
        refresh_token = self._text(previous.get("refresh_token"))

        if not refresh_token:
            return False

        response = self._post_form(
            TOKEN_URL,
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
        )

        self.save_tokens(response, previous=previous)

        log.info("Spotify: access token refreshed automatically")
        return True

    def get_access_token(self, authorize_if_needed=False):
        tokens = self.load_tokens()

        if self.token_is_valid(tokens):
            return self._text(tokens.get("access_token"))

        if self._text(tokens.get("refresh_token")):
            try:
                if self.refresh_access_token():
                    return self._text(
                        self.load_tokens().get("access_token")
                    )
            except Exception as error:
                log.error(
                    "Spotify automatic refresh failed: "
                    f"{type(error).__name__}: {error}"
                )

        if authorize_if_needed:
            self.ensure_authorized_async()

        return ""

    def ensure_authorized_async(
        self,
        on_success=None,
        on_error=None,
    ):
        """
        Ensure Spotify is authorized without blocking the Kivy UI.

        on_success is called after a valid Spotify account connection exists.
        on_error receives a readable error message when authorization fails.
        """
        if not SpotifyClientManager.has_client_id():
            message = (
                "Spotify Client ID is not configured."
            )
            log.info(
                "Spotify: Client ID not configured; "
                "authorization skipped"
            )

            if callable(on_error):
                from kivy.clock import Clock
                Clock.schedule_once(
                    lambda dt: on_error(message),
                    0,
                )

            return False

        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return True

            self._worker = threading.Thread(
                target=self._authorization_worker,
                args=(on_success, on_error),
                daemon=True,
                name="M12SpotifyAuth",
            )
            self._worker.start()

        return True

    def _authorization_worker(
        self,
        on_success=None,
        on_error=None,
    ):
        try:
            tokens = self.load_tokens()

            if self.token_is_valid(tokens):
                self._verify_profile(
                    tokens.get(
                        "access_token",
                        "",
                    )
                )
                self._notify_success(
                    on_success
                )
                return

            if self._text(
                tokens.get(
                    "refresh_token"
                )
            ):
                try:
                    if self.refresh_access_token():
                        tokens = self.load_tokens()
                        self._verify_profile(
                            tokens.get(
                                "access_token",
                                "",
                            )
                        )
                        self._notify_success(
                            on_success
                        )
                        return

                except Exception as error:
                    log.error(
                        "Spotify saved authorization "
                        "refresh failed: "
                        f"{type(error).__name__}: "
                        f"{error}"
                    )

            self._authorize_first_time()
            self._notify_success(
                on_success
            )

        except Exception as error:
            message = (
                f"{type(error).__name__}: {error}"
            )

            log.error(
                "Spotify authorization failed: "
                + message
            )

            self._notify_error(
                on_error,
                message,
            )

    @staticmethod
    def _notify_success(callback):
        if not callable(callback):
            return

        from kivy.clock import Clock

        Clock.schedule_once(
            lambda dt: callback(),
            0,
        )

    @staticmethod
    def _notify_error(
        callback,
        message,
    ):
        if not callable(callback):
            return

        from kivy.clock import Clock

        Clock.schedule_once(
            lambda dt: callback(
                str(message)
            ),
            0,
        )

    def _verify_profile(self, access_token):
        token = self._text(access_token)

        if not token:
            return False

        profile = self._get_json(PROFILE_URL, token)

        name = (
            self._text(profile.get("display_name"))
            or self._text(profile.get("id"))
            or "Spotify user"
        )
        product = self._text(profile.get("product"))

        suffix = f" ({product})" if product else ""

        log.info(
            f"Spotify: connected automatically as {name}{suffix}"
        )
        return True

    @staticmethod
    def _new_verifier():
        return secrets.token_urlsafe(64)

    @staticmethod
    def _challenge(verifier):
        digest = hashlib.sha256(
            verifier.encode("ascii")
        ).digest()

        return (
            base64.urlsafe_b64encode(digest)
            .decode("ascii")
            .rstrip("=")
        )

    @staticmethod
    def _open_browser(url):
        if kivy_platform == "android":
            try:
                from android import activity
                from jnius import autoclass

                Intent = autoclass("android.content.Intent")
                Uri = autoclass("android.net.Uri")

                intent = Intent(
                    Intent.ACTION_VIEW,
                    Uri.parse(url),
                )
                activity.startActivity(intent)
                return True

            except Exception as error:
                log.error(
                    "Spotify Android browser open failed: "
                    f"{type(error).__name__}: {error}"
                )
                return False

        try:
            return bool(webbrowser.open(url, new=2))
        except Exception as error:
            log.error(
                "Spotify browser open failed: "
                f"{type(error).__name__}: {error}"
            )
            return False

    def _authorize_first_time(self):
        with self._lock:
            if self._authorization_in_progress:
                return False
            self._authorization_in_progress = True

        try:
            client_id = SpotifyClientManager.get_client_id()

            if not client_id:
                raise RuntimeError(
                    "Spotify Client ID is not configured."
                )

            verifier = self._new_verifier()
            challenge = self._challenge(verifier)
            expected_state = secrets.token_urlsafe(24)

            result = {
                "code": "",
                "state": "",
                "error": "",
            }
            completed = threading.Event()

            class CallbackHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    parsed = urllib.parse.urlparse(self.path)

                    if parsed.path != REDIRECT_PATH:
                        self.send_response(404)
                        self.end_headers()
                        return

                    query = urllib.parse.parse_qs(parsed.query)

                    result["code"] = query.get("code", [""])[0]
                    result["state"] = query.get("state", [""])[0]
                    result["error"] = query.get("error", [""])[0]

                    body = (
                        "<html><body>"
                        "<h2>M12 OS</h2>"
                        "<p>Spotify authorization received. "
                        "You can return to M12.</p>"
                        "</body></html>"
                    ).encode("utf-8")

                    self.send_response(200)
                    self.send_header(
                        "Content-Type",
                        "text/html; charset=utf-8",
                    )
                    self.send_header(
                        "Content-Length",
                        str(len(body)),
                    )
                    self.end_headers()
                    self.wfile.write(body)
                    completed.set()

                def log_message(self, format, *args):
                    return

            class CallbackServer(ThreadingHTTPServer):
                allow_reuse_address = True

            server = CallbackServer(
                (REDIRECT_HOST, REDIRECT_PORT),
                CallbackHandler,
            )

            server_thread = threading.Thread(
                target=server.serve_forever,
                daemon=True,
                name="M12SpotifyCallback",
            )
            server_thread.start()

            try:
                params = {
                    "client_id": client_id,
                    "response_type": "code",
                    "redirect_uri": REDIRECT_URI,
                    "scope": " ".join(SCOPES),
                    "state": expected_state,
                    "code_challenge_method": "S256",
                    "code_challenge": challenge,
                }

                authorization_url = (
                    AUTHORIZE_URL
                    + "?"
                    + urllib.parse.urlencode(params)
                )

                log.info(
                    "Spotify: first authorization required; "
                    "opening Spotify automatically"
                )

                if not self._open_browser(authorization_url):
                    raise RuntimeError(
                        "Could not open Spotify authorization page."
                    )

                if not completed.wait(timeout=300):
                    raise TimeoutError(
                        "Spotify authorization timed out."
                    )

            finally:
                server.shutdown()
                server.server_close()

            if result["error"]:
                raise RuntimeError(
                    "Spotify authorization denied: "
                    + result["error"]
                )

            if result["state"] != expected_state:
                raise RuntimeError(
                    "Spotify authorization state verification failed."
                )

            code = self._text(result["code"])

            if not code:
                raise RuntimeError(
                    "Spotify returned no authorization code."
                )

            response = self._post_form(
                TOKEN_URL,
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                    "client_id": client_id,
                    "code_verifier": verifier,
                },
            )

            tokens = self.save_tokens(response)
            self._verify_profile(tokens.get("access_token", ""))

            log.info(
                "Spotify: first authorization completed and saved"
            )
            return True

        finally:
            with self._lock:
                self._authorization_in_progress = False


spotify_auth_service = SpotifyAuthService()