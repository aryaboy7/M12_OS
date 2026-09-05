import json
import re
import ssl
import subprocess
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher

import certifi

from services.spotify_auth_service import (
    spotify_auth_service,
)


SPOTIFY_SEARCH_URL = (
    "https://api.spotify.com/v1/search"
)
SPOTIFY_DEVICES_URL = (
    "https://api.spotify.com/v1/me/player/devices"
)
SPOTIFY_PLAY_URL = (
    "https://api.spotify.com/v1/me/player/play"
)
SPOTIFY_PAUSE_URL = (
    "https://api.spotify.com/v1/me/player/pause"
)


class SpotifyMusicService:
    """
    Spotify catalog search used by Recognized Songs.

    Search is deliberately multi-pass:
        1. Spotify field filters: track + artist
        2. Plain artist + title search
        3. Title-only fallback

    Returned candidates are ranked using general metadata similarity.
    No song-specific titles, artists, albums, or version names are hardcoded.
    """

    MINIMUM_MATCH_SCORE = 0.72

    @staticmethod
    def _is_android():
        try:
            from kivy.utils import platform
            return platform == "android"
        except Exception:
            return False

    @staticmethod
    def _ssl_context():
        return ssl.create_default_context(
            cafile=certifi.where()
        )

    @staticmethod
    def _text(value):
        return str(value or "").strip()

    @classmethod
    def _normalize(cls, value):
        text = unicodedata.normalize(
            "NFKD",
            cls._text(value),
        )
        text = "".join(
            char
            for char in text
            if not unicodedata.combining(char)
        )
        text = text.casefold()
        text = re.sub(
            r"[^\w]+",
            " ",
            text,
            flags=re.UNICODE,
        )
        return " ".join(text.split())

    @classmethod
    def _base_title(cls, value):
        """
        Generic alternate title form that removes trailing bracketed
        qualifiers, e.g. a mix/edit/version descriptor, without naming
        any particular song or descriptor.
        """
        text = cls._text(value)
        text = re.sub(
            r"\s*[\(\[].*?[\)\]]\s*$",
            "",
            text,
        ).strip()
        return text

    @classmethod
    def _ratio(cls, left, right):
        left_normalized = cls._normalize(left)
        right_normalized = cls._normalize(right)

        if not left_normalized or not right_normalized:
            return 0.0

        if left_normalized == right_normalized:
            return 1.0

        sequence_score = SequenceMatcher(
            None,
            left_normalized,
            right_normalized,
        ).ratio()

        left_tokens = set(
            left_normalized.split()
        )
        right_tokens = set(
            right_normalized.split()
        )

        token_score = 0.0

        if left_tokens and right_tokens:
            intersection = len(
                left_tokens & right_tokens
            )

            token_score = (
                2.0 * intersection
                / (
                    len(left_tokens)
                    + len(right_tokens)
                )
            )

        return max(
            sequence_score,
            token_score,
        )

    @classmethod
    def _title_ratio(
        cls,
        expected,
        actual,
    ):
        return max(
            cls._ratio(
                expected,
                actual,
            ),
            cls._ratio(
                cls._base_title(expected),
                actual,
            ),
            cls._ratio(
                expected,
                cls._base_title(actual),
            ),
            cls._ratio(
                cls._base_title(expected),
                cls._base_title(actual),
            ),
        )

    @classmethod
    def _spotify_artist_names(
        cls,
        item,
    ):
        artists = item.get(
            "artists",
            [],
        )

        if not isinstance(
            artists,
            list,
        ):
            return []

        names = []

        for artist in artists:
            if not isinstance(
                artist,
                dict,
            ):
                continue

            name = cls._text(
                artist.get("name")
            )

            if name:
                names.append(name)

        return names

    @classmethod
    def _artist_text(cls, item):
        return ", ".join(
            cls._spotify_artist_names(
                item
            )
        )

    @classmethod
    def _artist_ratio(
        cls,
        expected_artist,
        item,
    ):
        names = cls._spotify_artist_names(
            item
        )

        if not names:
            return 0.0

        combined = ", ".join(names)

        scores = [
            cls._ratio(
                expected_artist,
                combined,
            )
        ]

        # If Spotify separates a featured performer into another artist
        # object, compare the recognized artist against each performer too.
        scores.extend(
            cls._ratio(
                expected_artist,
                name,
            )
            for name in names
        )

        return max(scores)

    @classmethod
    def _album_text(cls, item):
        album = item.get(
            "album",
            {},
        )

        if not isinstance(
            album,
            dict,
        ):
            return ""

        return cls._text(
            album.get("name")
        )

    @classmethod
    def _score_item(
        cls,
        item,
        title,
        artist,
        album,
    ):
        spotify_title = cls._text(
            item.get("name")
        )
        spotify_artist = (
            cls._artist_text(item)
        )
        spotify_album = (
            cls._album_text(item)
        )

        title_score = cls._title_ratio(
            title,
            spotify_title,
        )

        artist_score = (
            cls._artist_ratio(
                artist,
                item,
            )
            if artist
            else 1.0
        )

        if album:
            album_score = cls._ratio(
                album,
                spotify_album,
            )

            score = (
                title_score * 0.60
                + artist_score * 0.35
                + album_score * 0.05
            )
        else:
            album_score = 0.0

            score = (
                title_score * 0.63
                + artist_score * 0.37
            )

        # Title remains essential.
        if title and title_score < 0.55:
            score *= 0.65

        # Artist remains essential when AudD supplied one.
        if artist and artist_score < 0.50:
            score *= 0.65

        return {
            "score": float(score),
            "title_score": float(
                title_score
            ),
            "artist_score": float(
                artist_score
            ),
            "album_score": float(
                album_score
            ),
            "spotify_title": (
                spotify_title
            ),
            "spotify_artist": (
                spotify_artist
            ),
            "spotify_album": (
                spotify_album
            ),
        }

    @staticmethod
    def _get_json(
        url,
        access_token,
    ):
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": (
                    f"Bearer {access_token}"
                ),
                "Accept": "application/json",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=30,
                context=SpotifyMusicService._ssl_context(),
            ) as response:
                body = response.read()

        except urllib.error.HTTPError as error:
            details = error.read().decode(
                "utf-8",
                errors="replace",
            )

            raise RuntimeError(
                "Spotify search HTTP "
                f"{error.code}: {details}"
            ) from error

        except urllib.error.URLError as error:
            raise RuntimeError(
                "Spotify search network error: "
                f"{error.reason}"
            ) from error

        try:
            data = json.loads(
                body.decode("utf-8")
            )
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "Spotify search returned invalid JSON."
            ) from error

        if not isinstance(data, dict):
            raise RuntimeError(
                "Spotify search returned "
                "an invalid response."
            )

        return data

    @classmethod
    def _search(
        cls,
        query,
        access_token,
    ):
        query = cls._text(query)

        if not query:
            return []

        params = {
            "q": query,
            "type": "track",
            "limit": "10",
        }

        url = (
            SPOTIFY_SEARCH_URL
            + "?"
            + urllib.parse.urlencode(
                params
            )
        )

        data = cls._get_json(
            url,
            access_token,
        )

        tracks = data.get(
            "tracks",
            {},
        )

        if not isinstance(
            tracks,
            dict,
        ):
            return []

        items = tracks.get(
            "items",
            [],
        )

        return (
            items
            if isinstance(
                items,
                list,
            )
            else []
        )

    @classmethod
    def _queries(
        cls,
        title,
        artist,
    ):
        """
        Return unique searches from narrowest to broadest.

        Spotify's documented field-filter form is:
            track:<title> artist:<artist>

        We intentionally do not use exact quoted values because recognition
        metadata and Spotify catalog metadata often differ slightly.
        """
        queries = []

        if title and artist:
            queries.append(
                f"track:{title} "
                f"artist:{artist}"
            )
            queries.append(
                f"{artist} {title}"
            )

        if title:
            queries.append(title)

        if artist and not title:
            queries.append(artist)

        unique = []
        seen = set()

        for query in queries:
            normalized = cls._normalize(
                query
            )

            if not normalized:
                continue

            if normalized in seen:
                continue

            seen.add(normalized)
            unique.append(query)

        return unique

    @classmethod
    def find_track(
        cls,
        title,
        artist,
        album="",
    ):
        """
        Return the strongest confident Spotify track match, or None.
        """
        title = cls._text(title)
        artist = cls._text(artist)
        album = cls._text(album)

        if not title and not artist:
            return None

        access_token = (
            spotify_auth_service
            .get_access_token(
                authorize_if_needed=False
            )
        )

        if not access_token:
            raise RuntimeError(
                "Spotify is not authorized."
            )

        candidates = {}

        for query in cls._queries(
            title,
            artist,
        ):
            for item in cls._search(
                query,
                access_token,
            ):
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                track_id = cls._text(
                    item.get("id")
                )

                if not track_id:
                    continue

                # Keep the first copy of each Spotify track.
                if track_id not in candidates:
                    candidates[
                        track_id
                    ] = item

        ranked = []

        for item in candidates.values():
            track_id = cls._text(
                item.get("id")
            )

            external_urls = item.get(
                "external_urls",
                {},
            )

            if not isinstance(
                external_urls,
                dict,
            ):
                external_urls = {}

            play_url = cls._text(
                external_urls.get(
                    "spotify"
                )
            )

            if not track_id or not play_url:
                continue

            scored = cls._score_item(
                item=item,
                title=title,
                artist=artist,
                album=album,
            )

            scored.update(
                {
                    "track_id": track_id,
                    "play_url": play_url,
                    "title": scored[
                        "spotify_title"
                    ],
                    "artist": scored[
                        "spotify_artist"
                    ],
                    "album": scored[
                        "spotify_album"
                    ],
                }
            )

            ranked.append(scored)

        if not ranked:
            return None

        ranked.sort(
            key=lambda item: (
                item["score"],
                item["title_score"],
                item["artist_score"],
            ),
            reverse=True,
        )

        best = ranked[0]

        if (
            best["score"]
            < cls.MINIMUM_MATCH_SCORE
        ):
            return None

        return best

    @staticmethod
    def _request_json_or_empty(
        url,
        access_token,
        method="GET",
        payload=None,
    ):
        body = None

        headers = {
            "Authorization": (
                f"Bearer {access_token}"
            ),
            "Accept": "application/json",
        }

        if payload is not None:
            body = json.dumps(
                payload
            ).encode("utf-8")
            headers[
                "Content-Type"
            ] = "application/json"

        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=30,
                context=SpotifyMusicService._ssl_context(),
            ) as response:
                raw = response.read()

        except urllib.error.HTTPError as error:
            details = error.read().decode(
                "utf-8",
                errors="replace",
            )

            raise RuntimeError(
                "Spotify playback HTTP "
                f"{error.code}: {details}"
            ) from error

        except urllib.error.URLError as error:
            raise RuntimeError(
                "Spotify playback network error: "
                f"{error.reason}"
            ) from error

        if not raw or not raw.strip():
            return {}

        decoded = raw.decode(
            "utf-8",
            errors="replace",
        ).strip()

        # Spotify player-control endpoints may return a successful
        # response with no JSON payload. Some clients/proxies can also
        # return a small non-JSON success body. A 2xx response has already
        # succeeded at this point, so only parse JSON when it actually
        # looks like JSON.
        if not decoded.startswith(
            ("{", "[")
        ):
            return {}

        try:
            data = json.loads(
                decoded
            )
        except json.JSONDecodeError:
            return {}

        if not isinstance(data, dict):
            return {}

        return data

    @classmethod
    def available_devices(cls):
        access_token = (
            spotify_auth_service
            .get_access_token(
                authorize_if_needed=False
            )
        )

        if not access_token:
            raise RuntimeError(
                "Spotify is not authorized."
            )

        data = cls._request_json_or_empty(
            SPOTIFY_DEVICES_URL,
            access_token,
            method="GET",
        )

        devices = data.get(
            "devices",
            [],
        )

        if not isinstance(
            devices,
            list,
        ):
            return []

        return [
            device
            for device in devices
            if isinstance(
                device,
                dict,
            )
        ]

    @classmethod
    def _choose_device(cls, devices):
        controllable = [
            device
            for device in devices
            if cls._text(
                device.get("id")
            )
            and not bool(
                device.get(
                    "is_restricted"
                )
            )
        ]

        if not controllable:
            return None

        for device in controllable:
            if bool(
                device.get("is_active")
            ):
                return device

        return controllable[0]

    @classmethod
    def _launch_spotify_app(cls):
        """
        Best-effort native Spotify app activation.

        Desktop Linux:
            1. spotify command
            2. Flatpak com.spotify.Client

        Android:
            Launch com.spotify.music via Android package manager.

        This method never opens the web browser.
        """
        try:
            from kivy.utils import platform
        except Exception:
            platform = ""

        if platform == "android":
            try:
                from jnius import autoclass

                PythonActivity = autoclass(
                    "org.kivy.android.PythonActivity"
                )

                activity = (
                    PythonActivity.mActivity
                )

                package_manager = (
                    activity.getPackageManager()
                )

                intent = (
                    package_manager
                    .getLaunchIntentForPackage(
                        "com.spotify.music"
                    )
                )

                if intent is None:
                    raise RuntimeError(
                        "Spotify app is not installed."
                    )

                activity.startActivity(intent)
                return True

            except Exception as error:
                raise RuntimeError(
                    "Could not launch Spotify app: "
                    f"{error}"
                ) from error

        launch_attempts = [
            ["spotify"],
            [
                "flatpak",
                "run",
                "com.spotify.Client",
            ],
        ]

        errors = []

        for command in launch_attempts:
            try:
                subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True

            except FileNotFoundError:
                errors.append(
                    f"{command[0]} not found"
                )

            except Exception as error:
                errors.append(
                    f"{command[0]}: {error}"
                )

        raise RuntimeError(
            "Spotify desktop app is not installed "
            "or could not be launched. "
            + "; ".join(errors)
        )

    @classmethod
    def _wait_for_device(
        cls,
        timeout_seconds=12.0,
        interval_seconds=1.0,
    ):
        """
        Wait briefly for a newly launched Spotify client to register
        as a Spotify Connect device.
        """
        deadline = (
            time.monotonic()
            + float(timeout_seconds)
        )

        while time.monotonic() < deadline:
            devices = cls.available_devices()
            device = cls._choose_device(
                devices
            )

            if device is not None:
                return device

            time.sleep(
                float(interval_seconds)
            )

        return None

    @classmethod
    def _find_device_by_id(
        cls,
        devices,
        device_id,
    ):
        wanted = cls._text(
            device_id
        )

        if not wanted:
            return None

        for device in devices:
            if cls._text(
                device.get("id")
            ) == wanted:
                if not bool(
                    device.get(
                        "is_restricted"
                    )
                ):
                    return device

        return None

    @classmethod
    def wait_for_new_device(
        cls,
        existing_device_ids,
        timeout_seconds=12.0,
        interval_seconds=1.0,
    ):
        """
        Wait for a Spotify Connect device whose ID was not present
        before the browser was opened.
        """
        existing = {
            cls._text(item)
            for item in (
                existing_device_ids
                or []
            )
            if cls._text(item)
        }

        deadline = (
            time.monotonic()
            + float(timeout_seconds)
        )

        while time.monotonic() < deadline:
            devices = cls.available_devices()

            for device in devices:
                device_id = cls._text(
                    device.get("id")
                )

                if (
                    device_id
                    and device_id not in existing
                    and not bool(
                        device.get(
                            "is_restricted"
                        )
                    )
                ):
                    return device

            time.sleep(
                float(interval_seconds)
            )

        return None

    @classmethod
    def play_track_on_device(
        cls,
        track_id,
        device_id,
    ):
        """
        Start one exact Spotify track on one exact Connect device.
        """
        track_id = cls._text(
            track_id
        )
        device_id = cls._text(
            device_id
        )

        if not track_id:
            raise RuntimeError(
                "This song has no Spotify track ID."
            )

        if not device_id:
            raise RuntimeError(
                "Spotify device ID is missing."
            )

        access_token = (
            spotify_auth_service
            .get_access_token(
                authorize_if_needed=False
            )
        )

        if not access_token:
            raise RuntimeError(
                "Spotify is not authorized."
            )

        devices = cls.available_devices()
        device = cls._find_device_by_id(
            devices,
            device_id,
        )

        if device is None:
            raise RuntimeError(
                "The requested Spotify device "
                "is no longer available."
            )

        url = (
            SPOTIFY_PLAY_URL
            + "?"
            + urllib.parse.urlencode(
                {
                    "device_id": device_id,
                }
            )
        )

        cls._request_json_or_empty(
            url,
            access_token,
            method="PUT",
            payload={
                "uris": [
                    (
                        "spotify:track:"
                        + track_id
                    )
                ]
            },
        )

        return {
            "device_id": device_id,
            "device_name": cls._text(
                device.get("name")
            ),
            "device_type": cls._text(
                device.get("type")
            ),
            "track_id": track_id,
        }

    @classmethod
    def play_track(
        cls,
        track_id,
    ):
        track_id = cls._text(
            track_id
        )

        if not track_id:
            raise RuntimeError(
                "This song has no Spotify track ID."
            )

        if cls._is_android():
            from services.spotify_android_remote_service import (
                spotify_android_remote_service,
            )

            return (
                spotify_android_remote_service
                .play_track(track_id)
            )

        access_token = (
            spotify_auth_service
            .get_access_token(
                authorize_if_needed=False
            )
        )

        if not access_token:
            raise RuntimeError(
                "Spotify is not authorized."
            )

        devices = cls.available_devices()
        device = cls._choose_device(
            devices
        )

        if device is None:
            cls._launch_spotify_app()

            device = cls._wait_for_device(
                timeout_seconds=12.0,
                interval_seconds=1.0,
            )

        if device is None:
            raise RuntimeError(
                "Spotify app was launched, but "
                "no Spotify Connect device "
                "became available."
            )

        device_id = cls._text(
            device.get("id")
        )

        url = (
            SPOTIFY_PLAY_URL
            + "?"
            + urllib.parse.urlencode(
                {
                    "device_id": device_id,
                }
            )
        )

        cls._request_json_or_empty(
            url,
            access_token,
            method="PUT",
            payload={
                "uris": [
                    (
                        "spotify:track:"
                        + track_id
                    )
                ]
            },
        )

        return {
            "device_id": device_id,
            "device_name": cls._text(
                device.get("name")
            ),
            "device_type": cls._text(
                device.get("type")
            ),
            "track_id": track_id,
        }
    @classmethod
    def _resolve_control_device(
        cls,
        devices,
        device_id="",
    ):
        requested_device_id = cls._text(
            device_id
        )

        if requested_device_id:
            device = cls._find_device_by_id(
                devices,
                requested_device_id,
            )

            if device is not None:
                return device

        return cls._choose_device(
            devices
        )

    @classmethod
    def pause_playback(
        cls,
        device_id="",
    ):
        if cls._is_android():
            from services.spotify_android_remote_service import (
                spotify_android_remote_service,
            )

            return (
                spotify_android_remote_service
                .pause_playback()
            )

        access_token = (
            spotify_auth_service
            .get_access_token(
                authorize_if_needed=False
            )
        )

        if not access_token:
            raise RuntimeError(
                "Spotify is not authorized."
            )

        devices = cls.available_devices()
        device = cls._resolve_control_device(
            devices,
            device_id=device_id,
        )

        if device is None:
            raise RuntimeError(
                "No available Spotify Connect device."
            )

        device_id = cls._text(
            device.get("id")
        )

        url = (
            SPOTIFY_PAUSE_URL
            + "?"
            + urllib.parse.urlencode(
                {
                    "device_id": device_id,
                }
            )
        )

        cls._request_json_or_empty(
            url,
            access_token,
            method="PUT",
        )

        return {
            "device_id": device_id,
            "device_name": cls._text(
                device.get("name")
            ),
        }

    @classmethod
    def resume_playback(
        cls,
        device_id="",
    ):
        """
        Resume Spotify playback at the current paused position.
        """
        if cls._is_android():
            from services.spotify_android_remote_service import (
                spotify_android_remote_service,
            )

            return (
                spotify_android_remote_service
                .resume_playback()
            )

        access_token = (
            spotify_auth_service
            .get_access_token(
                authorize_if_needed=False
            )
        )

        if not access_token:
            raise RuntimeError(
                "Spotify is not authorized."
            )

        devices = cls.available_devices()
        device = cls._resolve_control_device(
            devices,
            device_id=device_id,
        )

        if device is None:
            raise RuntimeError(
                "No available Spotify Connect device."
            )

        device_id = cls._text(
            device.get("id")
        )

        url = (
            SPOTIFY_PLAY_URL
            + "?"
            + urllib.parse.urlencode(
                {
                    "device_id": device_id,
                }
            )
        )

        cls._request_json_or_empty(
            url,
            access_token,
            method="PUT",
        )

        return {
            "device_id": device_id,
            "device_name": cls._text(
                device.get("name")
            ),
        }



spotify_music_service = (
    SpotifyMusicService()
)