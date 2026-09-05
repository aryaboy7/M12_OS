import os
import tempfile
import threading
import uuid
import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_VERSION = "1"


class RecognizedMusicDatabase:
    """
    XML database for songs successfully recognized by M12.

    A duplicate is the same:
        title + artist + album + recognition provider

    ID, recognition time, playback status, and playback URL are not
    part of duplicate matching.
    """

    def __init__(self, database_file=None):
        self._lock = threading.RLock()

        if database_file is None:
            self.database_file = self.default_database_file()
        else:
            self.database_file = Path(
                database_file
            ).expanduser()

        self.database_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._ensure_database()

    @classmethod
    def default_database_file(cls):
        """
        Desktop:
            <M12 project>/data/music/recognized_songs.xml

        Android:
            app-private writable storage/music/recognized_songs.xml
        """
        explicit_directory = os.getenv(
            "M12_RECOGNIZED_MUSIC_DIR",
            "",
        ).strip()

        if explicit_directory:
            return (
                Path(explicit_directory)
                .expanduser()
                / "recognized_songs.xml"
            )

        android_private = os.getenv(
            "ANDROID_PRIVATE",
            "",
        ).strip()

        if android_private:
            return (
                Path(android_private)
                / "music"
                / "recognized_songs.xml"
            )

        try:
            from kivy.utils import platform

            if platform == "android":
                kivy_directory = (
                    cls._kivy_user_data_dir()
                )

                if kivy_directory is not None:
                    return (
                        kivy_directory
                        / "music"
                        / "recognized_songs.xml"
                    )
        except Exception:
            pass

        return (
            BASE_DIR
            / "data"
            / "music"
            / "recognized_songs.xml"
        )

    @staticmethod
    def _kivy_user_data_dir():
        try:
            from kivy.app import App

            running_app = App.get_running_app()

            if running_app is None:
                return None

            user_data_dir = str(
                getattr(
                    running_app,
                    "user_data_dir",
                    "",
                )
            ).strip()

            if not user_data_dir:
                return None

            return Path(user_data_dir)

        except Exception:
            return None

    @staticmethod
    def _timestamp():
        return datetime.now().astimezone().isoformat(
            timespec="seconds"
        )

    @staticmethod
    def _identity_value(value):
        """
        Normalize only for duplicate comparison.
        Original text is preserved in the XML.
        """
        return " ".join(
            str(value or "").strip().split()
        ).casefold()

    @classmethod
    def _identity_key(
        cls,
        title,
        artist,
        album,
        recognition_provider,
    ):
        return (
            cls._identity_value(title),
            cls._identity_value(artist),
            cls._identity_value(album),
            cls._identity_value(
                recognition_provider
            ),
        )

    def _new_root(self):
        return ET.Element(
            "recognizedSongs",
            {
                "version": DATABASE_VERSION,
                "updatedAt": self._timestamp(),
            },
        )

    def _ensure_database(self):
        with self._lock:
            if self.database_file.is_file():
                try:
                    root = ET.parse(
                        self.database_file
                    ).getroot()

                    if root.tag == "recognizedSongs":
                        return

                except Exception as error:
                    print(
                        "[RecognizedMusicDatabase] "
                        "invalid XML: "
                        f"{type(error).__name__}: "
                        f"{error}"
                    )

            self._write_root(
                self._new_root()
            )

    def _load_root(self):
        try:
            root = ET.parse(
                self.database_file
            ).getroot()

            if root.tag != "recognizedSongs":
                raise ValueError(
                    "Unexpected XML root element."
                )

            return root

        except Exception as error:
            print(
                "[RecognizedMusicDatabase] "
                "load error: "
                f"{type(error).__name__}: "
                f"{error}"
            )

            root = self._new_root()
            self._write_root(root)
            return root

    @staticmethod
    def _element_text(parent, tag):
        element = parent.find(tag)

        if (
            element is None
            or element.text is None
        ):
            return ""

        return str(element.text).strip()

    @classmethod
    def _song_to_dict(cls, song):
        playback = song.find("playback")

        if playback is None:
            playback_provider = ""
            status = "not_found"
            track_id = ""
            play_url = ""
        else:
            playback_provider = (
                cls._element_text(
                    playback,
                    "provider",
                )
            )
            status = (
                cls._element_text(
                    playback,
                    "status",
                )
                or "not_found"
            )
            track_id = cls._element_text(
                playback,
                "trackId",
            )
            play_url = cls._element_text(
                playback,
                "playUrl",
            )

        return {
            "id": str(
                song.get("id", "")
            ).strip(),
            "title": cls._element_text(
                song,
                "title",
            ),
            "artist": cls._element_text(
                song,
                "artist",
            ),
            "album": cls._element_text(
                song,
                "album",
            ),
            "recognition_provider": (
                cls._element_text(
                    song,
                    "recognitionProvider",
                )
            ),
            "recognized_at": (
                cls._element_text(
                    song,
                    "recognizedAt",
                )
            ),
            "playback_provider": (
                playback_provider
            ),
            "status": status,
            "track_id": track_id,
            "play_url": play_url,
        }

    def _find_duplicate(
        self,
        root,
        title,
        artist,
        album,
        recognition_provider,
    ):
        wanted = self._identity_key(
            title=title,
            artist=artist,
            album=album,
            recognition_provider=(
                recognition_provider
            ),
        )

        for song in root.findall("song"):
            existing = self._identity_key(
                title=self._element_text(
                    song,
                    "title",
                ),
                artist=self._element_text(
                    song,
                    "artist",
                ),
                album=self._element_text(
                    song,
                    "album",
                ),
                recognition_provider=(
                    self._element_text(
                        song,
                        "recognitionProvider",
                    )
                ),
            )

            if existing == wanted:
                return song

        return None

    def add_recognition(self, result):
        """
        Add one successful recognition.

        New records always start:
            status = not_found
            playback provider = amazon_music
            play URL = empty

        Returns:
            {
                "saved": bool,
                "duplicate": bool,
                "song": dict | None
            }
        """
        if not isinstance(result, dict):
            return {
                "saved": False,
                "duplicate": False,
                "song": None,
            }

        if not bool(result.get("success")):
            return {
                "saved": False,
                "duplicate": False,
                "song": None,
            }

        title = str(
            result.get("title", "")
        ).strip()

        artist = str(
            result.get("artist", "")
        ).strip()

        album = str(
            result.get("album", "")
        ).strip()

        recognition_provider = str(
            result.get("provider", "")
        ).strip()

        if not title and not artist:
            return {
                "saved": False,
                "duplicate": False,
                "song": None,
            }

        with self._lock:
            root = self._load_root()

            duplicate = self._find_duplicate(
                root=root,
                title=title,
                artist=artist,
                album=album,
                recognition_provider=(
                    recognition_provider
                ),
            )

            if duplicate is not None:
                return {
                    "saved": False,
                    "duplicate": True,
                    "song": deepcopy(
                        self._song_to_dict(
                            duplicate
                        )
                    ),
                }

            song = ET.SubElement(
                root,
                "song",
                {
                    "id": uuid.uuid4().hex,
                },
            )

            ET.SubElement(
                song,
                "title",
            ).text = title

            ET.SubElement(
                song,
                "artist",
            ).text = artist

            ET.SubElement(
                song,
                "album",
            ).text = album

            ET.SubElement(
                song,
                "recognitionProvider",
            ).text = recognition_provider

            ET.SubElement(
                song,
                "recognizedAt",
            ).text = self._timestamp()

            playback = ET.SubElement(
                song,
                "playback",
            )

            ET.SubElement(
                playback,
                "provider",
            ).text = "amazon_music"

            ET.SubElement(
                playback,
                "status",
            ).text = "not_found"

            ET.SubElement(
                playback,
                "playUrl",
            ).text = ""

            root.set(
                "version",
                DATABASE_VERSION,
            )

            root.set(
                "updatedAt",
                self._timestamp(),
            )

            self._write_root(root)

            return {
                "saved": True,
                "duplicate": False,
                "song": deepcopy(
                    self._song_to_dict(song)
                ),
            }

    def list_songs(self):
        """
        Return all records, newest first.
        """
        with self._lock:
            root = self._load_root()

            songs = [
                self._song_to_dict(song)
                for song in root.findall("song")
            ]

        return list(
            reversed(songs)
        )

    def mark_playback_found(
        self,
        song_id,
        play_url,
        provider="amazon_music",
        track_id="",
    ):
        """
        Mark one existing record as having a usable playback link.

        This is provider-agnostic apart from the default provider name.
        It does not search for music; it only stores a verified result.

        Returns the updated song dict, or None when the ID is not found.
        """
        target_id = str(
            song_id or ""
        ).strip()

        target_url = str(
            play_url or ""
        ).strip()

        playback_provider = str(
            provider or ""
        ).strip()

        playback_track_id = str(
            track_id or ""
        ).strip()

        if not target_id or not target_url:
            return None

        with self._lock:
            root = self._load_root()

            target = None

            for song in root.findall("song"):
                if str(
                    song.get("id", "")
                ).strip() == target_id:
                    target = song
                    break

            if target is None:
                return None

            playback = target.find("playback")

            if playback is None:
                playback = ET.SubElement(
                    target,
                    "playback",
                )

            provider_element = playback.find(
                "provider"
            )

            if provider_element is None:
                provider_element = ET.SubElement(
                    playback,
                    "provider",
                )

            provider_element.text = (
                playback_provider
                or "amazon_music"
            )

            status_element = playback.find(
                "status"
            )

            if status_element is None:
                status_element = ET.SubElement(
                    playback,
                    "status",
                )

            status_element.text = "found"

            track_element = playback.find(
                "trackId"
            )

            if track_element is None:
                track_element = ET.SubElement(
                    playback,
                    "trackId",
                )

            track_element.text = (
                playback_track_id
            )

            url_element = playback.find(
                "playUrl"
            )

            if url_element is None:
                url_element = ET.SubElement(
                    playback,
                    "playUrl",
                )

            url_element.text = target_url

            root.set(
                "version",
                DATABASE_VERSION,
            )

            root.set(
                "updatedAt",
                self._timestamp(),
            )

            self._write_root(root)

            return deepcopy(
                self._song_to_dict(
                    target
                )
            )

    def delete_song(self, song_id):
        """
        Delete exactly one recognized-song record by database ID.

        Returns True only when a record was removed.
        """
        target_id = str(
            song_id or ""
        ).strip()

        if not target_id:
            return False

        with self._lock:
            root = self._load_root()

            target = None

            for song in root.findall("song"):
                if str(
                    song.get("id", "")
                ).strip() == target_id:
                    target = song
                    break

            if target is None:
                return False

            root.remove(target)

            root.set(
                "version",
                DATABASE_VERSION,
            )

            root.set(
                "updatedAt",
                self._timestamp(),
            )

            self._write_root(root)
            return True

    def count(self):
        with self._lock:
            root = self._load_root()

            return len(
                root.findall("song")
            )

    def _write_root(self, root):
        self.database_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        tree = ET.ElementTree(root)

        try:
            ET.indent(
                tree,
                space="    ",
            )
        except AttributeError:
            pass

        file_descriptor, temporary_name = (
            tempfile.mkstemp(
                prefix="recognized_songs_",
                suffix=".xml",
                dir=str(
                    self.database_file.parent
                ),
            )
        )

        os.close(file_descriptor)

        temporary_path = Path(
            temporary_name
        )

        try:
            tree.write(
                temporary_path,
                encoding="utf-8",
                xml_declaration=True,
            )

            os.replace(
                temporary_path,
                self.database_file,
            )

        finally:
            if temporary_path.exists():
                try:
                    temporary_path.unlink()
                except Exception:
                    pass