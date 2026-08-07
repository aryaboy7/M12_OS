import re
from typing import Any

from services.screen_helper import ScreenHelper
from services.skills.base_skill import BaseSkill, SkillResult


class MusicSkill(BaseSkill):
    """Button-for-button AI control for the M12OS Music screen."""

    name = "music"
    priority = 2
    SCREEN_NAMES = ("music", "music_player", "media")

    COMMANDS = {
        "open": {"music", "open music", "show music", "music player", "open music player"},
        "audio": {"audio", "open audio", "show audio", "open audio files"},
        "video": {"video", "videos", "open video", "show video", "open videos"},
        "downloads": {"downloads", "open downloads", "show downloads"},
        "favorites": {"favorites", "open favorites", "show favorites", "open music favorites"},
        "internal": {"internal storage", "open internal", "show internal", "use internal storage"},
        "external": {"external storage", "open external", "show external", "use external storage"},
        "play": {"play", "play music", "play audio", "start music", "start audio", "плей", "лей", "лейк"},
        "pause": {"pause", "pause music", "pause audio", "пауза"},
        "resume": {"resume", "resume music", "continue music", "continue playing"},
        "stop": {"stop", "stop music", "stop audio", "stop playing"},
        "next": {"next", "next song", "next track", "play next", "skip song"},
        "previous": {"previous", "previous song", "previous track", "play previous"},
        "random": {"play random", "random song", "play random music"},
        "play_favorites": {"play favorites", "play favorite songs", "play my favorites"},
        "shuffle_on": {"shuffle on", "turn shuffle on", "enable shuffle"},
        "shuffle_off": {"shuffle off", "turn shuffle off", "disable shuffle"},
        "repeat_off": {"repeat off", "turn repeat off"},
        "repeat_one": {"repeat one", "repeat song", "repeat this song"},
        "repeat_all": {"repeat all", "repeat playlist"},
        "add_favorite": {"add to favorites", "add song to favorites", "favorite this song"},
        "remove_favorite": {"remove from favorites", "remove song from favorites", "unfavorite this song"},
        "rescan": {"rescan", "rescan music", "refresh music", "scan music"},
        "clear_search": {"clear search", "clear music search"},
        "volume_up": {"volume up", "music volume up", "increase volume"},
        "volume_down": {"volume down", "music volume down", "decrease volume"},
        "mute": {"mute", "mute music", "volume zero"},
        "current": {"what is playing", "what song is playing", "current song", "current track"},
        "back": {"music back", "back from music", "close music"},
    }

    PLAY_PREFIXES = (
        "play song ", "play track ", "play music ", "play ",
        "включи песню ", "включи трек ", "сыграй ",
    )
    SEARCH_PREFIXES = (
        "search music for ", "search for ", "find song ", "find music ",
    )
    VOLUME_PATTERNS = (
        r"^(?:set\s+)?(?:music\s+)?volume(?:\s+to)?\s+(\d{1,3})\s*%?$",
        r"^volume\s+(\d{1,3})\s*%?$",
    )

    def can_handle(self, message: str, context: Any) -> float:
        text = self._normalize(message)
        if not text:
            return 0.0
        if self._command(text) or self._volume(text) is not None:
            return 1.0
        if self._prefix_value(text, self.PLAY_PREFIXES) or self._prefix_value(text, self.SEARCH_PREFIXES):
            return 0.99
        if any(word in text for word in ("music", "song", "track", "audio", "video", "favorite")):
            return 0.86
        return 0.0

    def handle(self, message: str, context: Any) -> SkillResult:
        original = str(message).strip()
        text = self._normalize(original)
        command = self._command(text)

        if command in {"open", "audio", "video", "downloads", "favorites", "internal", "external"}:
            opened, screen = self._screen(context, open_it=True)
            if not opened or screen is None:
                return self._result(False, "I couldn't open Music.", "open_music")

            folders = {"audio": "Audio", "video": "Video", "downloads": "Downloads", "favorites": "Favorites"}
            storages = {"internal": "Internal", "external": "External"}
            success = True
            if command in folders:
                success, _ = ScreenHelper.call(screen, "set_folder", folders[command])
            elif command in storages:
                success, _ = ScreenHelper.call(screen, "set_storage", storages[command])

            names = {
                "open": "Music", "audio": "Audio", "video": "Video",
                "downloads": "Downloads", "favorites": "Favorites",
                "internal": "Internal storage", "external": "External storage",
            }
            return self._result(success, f"{names[command]} opened.", f"open_{command}")

        ok, screen = self._screen(context, open_it=False)
        if not ok or screen is None:
            return self._result(False, "The Music screen is unavailable.", "music_error")

        method_commands = {
            "play": ("request_play_audio", (), "Music started."),
            "pause": ("pause_media", (None,), "Music paused."),
            "resume": ("resume_media", (None,), "Music resumed."),
            "stop": ("stop_media", (None,), "Music stopped."),
            "next": ("play_next", (None,), "Playing the next song."),
            "previous": ("play_previous", (None,), "Playing the previous song."),
            "random": ("play_random", (), "Playing a random song."),
            "play_favorites": ("request_play_favorites", (), "Playing favorite music."),
            "shuffle_on": ("set_shuffle", (True,), "Shuffle is on."),
            "shuffle_off": ("set_shuffle", (False,), "Shuffle is off."),
            "repeat_off": ("set_repeat_mode", ("OFF",), "Repeat is off."),
            "repeat_one": ("set_repeat_mode", ("ONE",), "Repeat one is on."),
            "repeat_all": ("set_repeat_mode", ("ALL",), "Repeat all is on."),
            "add_favorite": ("add_selected_to_favorites", (), "Added to Favorites."),
            "remove_favorite": ("remove_selected_from_favorites", (), "Removed from Favorites."),
            "rescan": ("rescan_media", (), "Music scan started."),
            "clear_search": ("clear_media_search", (), "Music search cleared."),
            "volume_up": ("volume_up", (), "Music volume increased."),
            "volume_down": ("volume_down", (), "Music volume decreased."),
            "mute": ("mute_volume", (), "Music muted."),
            "back": ("go_back", (None,), "Music closed."),
        }

        if command in method_commands:
            method, args, answer = method_commands[command]
            called, result = ScreenHelper.call(screen, method, *args)
            success = called and result is not False
            song = self._current_song(screen)
            if command in {"play", "next", "previous", "random", "play_favorites"} and song:
                answer = f"Playing: {song}."
            return self._result(success, answer, command, {"song": song})

        if command == "current":
            song = self._current_song(screen)
            if not song:
                answer = "No song is selected."
            elif bool(getattr(screen, "is_paused", False)):
                answer = f"Paused: {song}."
            elif bool(getattr(screen, "is_playing", False)):
                answer = f"Now playing: {song}."
            else:
                answer = f"Selected: {song}."
            return SkillResult(handled=True, answer=answer, confidence=1.0, action="current_song")

        volume = self._volume(text)
        if volume is not None:
            called, result = ScreenHelper.call(screen, "set_volume", volume)
            actual = int(result) if called and result is not None else volume
            return self._result(called and result is not None, f"Music volume set to {actual}%.", "music_volume", {"volume": actual})

        search = self._prefix_value(text, self.SEARCH_PREFIXES)
        if search:
            called, result = ScreenHelper.call(screen, "search_media", search)
            return self._result(called and result is not False, f'Searching music for "{search}".', "search_music", {"query": search})

        song_query = self._prefix_value(text, self.PLAY_PREFIXES)
        if song_query:
            called, result = ScreenHelper.call(screen, "play_by_name", song_query)
            song = self._current_song(screen)
            return self._result(called and bool(result), f"Playing: {song or song_query}.", "play_song_by_name", {"query": song_query})

        return SkillResult(handled=False, confidence=0.0)

    @classmethod
    def _command(cls, text):
        for name, phrases in cls.COMMANDS.items():
            if text in phrases:
                return name
        return None

    @staticmethod
    def _normalize(message):
        text = str(message).strip().lower().replace("’", "'")
        joined = {
            "openmusic": "open music", "openaudio": "open audio", "openvideo": "open video",
            "opendownloads": "open downloads", "openfavorites": "open favorites",
            "playaudio": "play audio", "playfavorites": "play favorites",
            "pausemusic": "pause music", "resumemusic": "resume music",
            "stopmusic": "stop music", "nextsong": "next song", "previoussong": "previous song",
            "shuffleon": "shuffle on", "shuffleoff": "shuffle off",
            "repeatone": "repeat one", "repeatall": "repeat all", "repeatoff": "repeat off",
            "volumeup": "volume up", "volumedown": "volume down",
        }
        compact = re.sub(r"[^a-zа-яё0-9]+", "", text)
        text = joined.get(compact, text)
        text = re.sub(r"[!?;,]+", " ", text)
        text = re.sub(r"\.(?=\s*$)", "", text)
        return " ".join(text.split())

    @classmethod
    def _volume(cls, text):
        for pattern in cls.VOLUME_PATTERNS:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                return max(0, min(100, int(match.group(1))))
        return None

    @staticmethod
    def _prefix_value(text, prefixes):
        for prefix in prefixes:
            if text.startswith(prefix):
                return text[len(prefix):].strip(' "\'.,!?')
        return ""

    @classmethod
    def _screen(cls, context, open_it):
        ok, screen, _ = ScreenHelper.find_screen(context, cls.SCREEN_NAMES, open_it=open_it)
        return ok, screen

    @staticmethod
    def _current_song(screen):
        called, result = ScreenHelper.call(screen, "current_song_name")
        if called:
            return str(result or "").strip()
        selected = getattr(screen, "selected_file", None)
        return str(getattr(selected, "name", selected) or "").strip()

    @staticmethod
    def _result(success, answer, action, data=None):
        return SkillResult(
            handled=True,
            answer=answer if success else f"Command failed: {action}.",
            confidence=1.0,
            action=action,
            data={**(data or {}), "success": bool(success)},
        )
