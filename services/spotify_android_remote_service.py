from kivy.utils import platform

from services.spotify_auth_service import REDIRECT_URI
from services.spotify_client_manager import SpotifyClientManager


class SpotifyAndroidRemoteService:
    """
    Android-only Spotify playback control.

    Python sends an explicit in-app Android broadcast using only standard
    Android framework classes. Android then loads M12's native Spotify
    receiver/bridge itself, avoiding PyJNIus secondary-DEX class loading.
    """

    ACTION_CONTROL = (
        "com.m12os.m12os.SPOTIFY_CONTROL"
    )

    RECEIVER_CLASS = (
        "com.m12os.m12os.SpotifyControlReceiver"
    )

    @staticmethod
    def _require_android():
        if platform != "android":
            raise RuntimeError(
                "Spotify Android control is only available on Android."
            )

    @staticmethod
    def _activity():
        from jnius import autoclass

        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )

        return PythonActivity.mActivity

    @classmethod
    def _send(
        cls,
        command,
        track_id="",
    ):
        cls._require_android()

        client_id = (
            SpotifyClientManager.get_client_id()
        )

        if not client_id:
            raise RuntimeError(
                "Spotify Client ID is not configured."
            )

        from jnius import autoclass

        Intent = autoclass(
            "android.content.Intent"
        )
        Bundle = autoclass(
            "android.os.Bundle"
        )

        activity = cls._activity()

        intent = Intent(
            cls.ACTION_CONTROL
        )

        intent.setClassName(
            str(activity.getPackageName()),
            cls.RECEIVER_CLASS,
        )

        extras = Bundle()
        extras.putString(
            "command",
            str(command),
        )
        extras.putString(
            "client_id",
            str(client_id),
        )
        extras.putString(
            "redirect_uri",
            str(REDIRECT_URI),
        )
        extras.putString(
            "track_id",
            str(track_id or ""),
        )

        intent.putExtras(extras)

        activity.sendBroadcast(
            intent
        )

        return True

    @classmethod
    def play_track(
        cls,
        track_id,
    ):
        track_id = str(
            track_id or ""
        ).strip()

        if not track_id:
            raise RuntimeError(
                "This song has no Spotify track ID."
            )

        cls._send(
            "PLAY",
            track_id,
        )

        return {
            "device_id": "android-app-remote",
            "device_name": "Spotify Android",
            "device_type": "Smartphone",
            "track_id": track_id,
        }

    @classmethod
    def pause_playback(cls):
        cls._send("PAUSE")

        return {
            "device_id": "android-app-remote",
            "device_name": "Spotify Android",
        }

    @classmethod
    def resume_playback(cls):
        cls._send("RESUME")

        return {
            "device_id": "android-app-remote",
            "device_name": "Spotify Android",
        }

    @classmethod
    def stop_playback(cls):
        cls._send("STOP")

        return {
            "device_id": "android-app-remote",
            "device_name": "Spotify Android",
        }

    @classmethod
    def disconnect(cls):
        # The native bridge keeps the App Remote connection while M12 is
        # running so PLAY/PAUSE/RESUME remain immediate.
        return None


spotify_android_remote_service = (
    SpotifyAndroidRemoteService()
)