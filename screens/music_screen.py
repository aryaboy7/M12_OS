from pathlib import Path
import atexit
import json
import os
import random
import signal
import subprocess
import sys

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.utils import platform
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput

try:
    from jnius import autoclass
except Exception:
    autoclass = None

from utils.logger import log
from utils.storage_roots import load_storage_roots
from utils.ui_scale import (
    title_font,
    button_font,
    list_font,
    text_font,
    status_font,
    input_font,
    row_height,
    button_height,
    input_height,
    padding_size,
    spacing_size,
)


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_MUSIC_DIR = BASE_DIR / "data" / "music"
DATA_MUSIC_DIR.mkdir(parents=True, exist_ok=True)
FAVORITES_FILE = DATA_MUSIC_DIR / "favorites.json"
PLAYER_STATUS_FILE = DATA_MUSIC_DIR / "player_status.json"

if platform == "macosx":
    MEDIA_FOLDERS = {
        "Audio": Path.home() / "Music",
        "Video": Path.home() / "Movies",
        "Downloads": Path.home() / "Downloads",
        "Desktop": Path.home() / "Desktop",
    }
elif platform == "android":
    MEDIA_FOLDERS = {
        "Audio": Path("/storage/emulated/0/Music"),
        "Video": Path("/storage/emulated/0/Movies"),
        "Downloads": Path("/storage/emulated/0/Download"),
    }

else:
    MEDIA_FOLDERS = {
        "Music": DATA_MUSIC_DIR,
    }

AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".aac", ".wav", ".ogg", ".aif", ".aiff", ".flac",
    ".mp2", ".mpga", ".caf", ".alac", ".m4b", ".m4p", ".wma"
}
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".3gp", ".mpeg", ".mpg"
}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


def existing_folders(candidates, fallback_first=True):
    folders = []

    for p in candidates:
        try:
            if p.exists() and p.is_dir():
                folders.append(p)
        except Exception:
            pass

    if not folders and fallback_first and candidates:
        folders.append(candidates[0])

    return folders


def android_roots_for_storage(storage="Internal"):
    roots = load_storage_roots()

    internal_root = Path(
        roots.get("internal_root", "/storage/emulated/0")
        or "/storage/emulated/0"
    )
    external_root = Path(
        roots.get("external_root", "/mnt/sdcard")
        or "/mnt/sdcard"
    )

    if storage == "External":
        return [external_root]

    if storage == "Both":
        return [internal_root, external_root]

    return [internal_root]


def android_media_folders(storage, names):
    candidates = []

    for root in android_roots_for_storage(storage):
        for name in names:
            candidates.append(root / name)

    return existing_folders(candidates, fallback_first=False)


def android_audio_folders(storage="Internal"):
    return android_media_folders(storage, ["Music", "Audio"])


def audio_folders(storage="Internal"):
    if platform == "android":
        return android_audio_folders(storage)

    candidates = [
        Path.home() / "Music",
        Path.home() / "Audio",
    ]

    return existing_folders(candidates)


def video_folders(storage="Internal"):
    if platform == "android":
        return android_media_folders(storage, ["Movies", "Video"])

    candidates = [
        Path.home() / "Movies",
        Path.home() / "Video",
    ]

    return existing_folders(candidates)


def download_folders(storage="Internal"):
    if platform == "android":
        return android_media_folders(storage, ["Download", "Downloads"])

    candidates = [
        Path.home() / "Download",
        Path.home() / "Downloads",
    ]

    return existing_folders(candidates)

REPEAT_OFF = "OFF"
REPEAT_ONE = "ONE"
REPEAT_ALL = "ALL"


EXTERNAL_PLAYERS = []


def register_external_player(proc):
    if proc and proc not in EXTERNAL_PLAYERS:
        EXTERNAL_PLAYERS.append(proc)


def kill_external_players():
    for proc in list(EXTERNAL_PLAYERS):
        try:
            if proc.poll() is None:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                else:
                    proc.terminate()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        try:
            EXTERNAL_PLAYERS.remove(proc)
        except Exception:
            pass


def _cleanup_on_exit():
    kill_external_players()


def _signal_cleanup(signum, frame):
    kill_external_players()
    sys.exit(0)


atexit.register(_cleanup_on_exit)

try:
    signal.signal(signal.SIGTERM, _signal_cleanup)
    signal.signal(signal.SIGINT, _signal_cleanup)
except Exception:
    pass



class MusicScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.media_files = []
        self.visible_files = []
        self.favorite_paths = set()
        self.selected_file = None
        self.sound = None
        self.player_process = None
        self.android_player = None
        self.folder_popup = None
        self.folder_current_path = None
        self.is_starting = False
        self.file_buttons = {}

        app = App.get_running_app()
        if app:
            try:
                app.bind(on_stop=self.on_app_stop)
            except Exception:
                pass

        self.active_storage = "Internal" if platform == "android" else "Local"
        self.active_folder = "Audio" if platform == "android" else "All"
        self.search_text = ""
        self.is_playing = False
        self.shuffle_on = False
        self.repeat_mode = REPEAT_OFF

        self.last_scan_total_files = 0
        self.last_scan_supported = 0
        self.last_scan_unsupported = 0
        self.last_scan_errors = 0

        root = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size(),
        )

        root.add_widget(Label(
            text="Music / Video",
            font_size=title_font(),
            bold=True,
            size_hint=(1, 0.035),
        ))

        self.now_label = Label(
            text="No file selected",
            font_size=text_font(),
            size_hint=(1, 0.04),
            halign="center",
            valign="middle",
        )
        self.now_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        root.add_widget(self.now_label)

        self.storage_buttons = {}

        if platform == "android":
            storage_row = BoxLayout(
                orientation="horizontal",
                spacing=spacing_size(),
                size_hint=(1, None),
                height=self.control_height(),
            )

            for name in ["Internal", "External"]:
                btn = Button(
                    text=name,
                    font_size=max(14, int(button_font() * 0.72)),
                    background_normal="",
                    background_color=(0.10, 0.45, 0.20, 1)
                    if name == self.active_storage
                    else (0.10, 0.15, 0.25, 1),
                )
                btn.bind(on_press=lambda inst, n=name: self.set_storage(n))
                storage_row.add_widget(btn)
                self.storage_buttons[name] = btn

            root.add_widget(storage_row)

        folder_row = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=self.control_height(),
        )

        self.folder_buttons = {}
        folder_names = (
            ["Audio", "Video", "Downloads", "Favorites"]
            if platform == "android"
            else ["All", "Favorites"] + list(MEDIA_FOLDERS.keys())
        )

        for name in folder_names:
            btn = Button(
                text=name,
                font_size=max(14, int(button_font() * 0.72)),
                background_normal="",
                background_color=(0.25, 0.45, 0.75, 1)
                if name == self.active_folder
                else (0.10, 0.15, 0.25, 1),
            )
            btn.bind(on_press=lambda inst, n=name: self.set_folder(n))
            folder_row.add_widget(btn)
            self.folder_buttons[name] = btn

        root.add_widget(folder_row)

        search_row = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=self.search_height(),
        )

        self.search_input = TextInput(
            hint_text="Search media...",
            text="",
            font_size=max(14, int(input_font() * 0.72)),
            multiline=False,
            use_bubble=False,
            use_handles=False,
            size_hint=(0.75, 1),
        )
        self.search_input.bind(text=self.on_search_text_delayed)
        search_row.add_widget(self.search_input)

        clear_search_btn = Button(
            text="Clear",
            font_size=max(14, int(button_font() * 0.72)),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1),
            size_hint=(0.25, 1),
        )
        clear_search_btn.bind(on_press=self.clear_search)
        search_row.add_widget(clear_search_btn)

        root.add_widget(search_row)

        self.song_scroll = ScrollView(
            size_hint=(1, 0.58),
            do_scroll_x=False,
            do_scroll_y=True,
        )

        self.file_list = GridLayout(
            cols=1,
            spacing=spacing_size(),
            size_hint_y=None,
        )
        self.file_list.bind(minimum_height=self.file_list.setter("height"))

        self.song_scroll.add_widget(self.file_list)
        root.add_widget(self.song_scroll)

        nav_row = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=self.control_height(),
        )

        prev_btn = self.make_button("<< Prev", (0.55, 0.45, 0.10, 1))
        prev_btn.bind(on_press=self.play_previous)
        nav_row.add_widget(prev_btn)

        self.play_btn = self.make_button("Play", (0.10, 0.45, 0.20, 1))
        self.play_btn.bind(on_press=self.play_selected)
        nav_row.add_widget(self.play_btn)

        next_btn = self.make_button("Next >>", (0.55, 0.45, 0.10, 1))
        next_btn.bind(on_press=self.play_next)
        nav_row.add_widget(next_btn)

        root.add_widget(nav_row)

        mode_row = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=self.control_height(),
        )

        self.shuffle_btn = self.make_button("Shuffle OFF", (0.12, 0.20, 0.35, 1))
        self.shuffle_btn.bind(on_press=self.toggle_shuffle)
        mode_row.add_widget(self.shuffle_btn)

        self.repeat_btn = self.make_button("Repeat OFF", (0.12, 0.20, 0.35, 1))
        self.repeat_btn.bind(on_press=self.cycle_repeat)
        mode_row.add_widget(self.repeat_btn)

        fav_btn = self.make_button("Favorite", (0.42, 0.28, 0.12, 1))
        fav_btn.bind(on_press=self.toggle_favorite)
        mode_row.add_widget(fav_btn)

        root.add_widget(mode_row)

        controls2 = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=self.control_height(),
        )

        stop_btn = self.make_button("Stop", (0.35, 0.12, 0.12, 1))
        stop_btn.bind(on_press=self.stop_media)
        controls2.add_widget(stop_btn)

        refresh_btn = self.make_button("Rescan", (0.12, 0.20, 0.35, 1))
        refresh_btn.bind(on_press=self.refresh_media)
        controls2.add_widget(refresh_btn)

        back_btn = self.make_button("< Back", (0.10, 0.15, 0.25, 1))
        back_btn.bind(on_press=self.go_back)
        controls2.add_widget(back_btn)

        root.add_widget(controls2)

        volume_row = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, 0.04),
        )

        volume_label = Label(
            text="Volume",
            font_size=status_font(),
            size_hint=(0.28, 1),
            halign="center",
            valign="middle",
        )
        volume_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        volume_row.add_widget(volume_label)

        self.volume_slider = Slider(
            min=0,
            max=1,
            value=0.8,
            size_hint=(0.72, 1),
        )
        self.volume_slider.bind(value=self.change_volume)
        volume_row.add_widget(self.volume_slider)

        root.add_widget(volume_row)

        self.status_label = Label(
            text=self.folder_text(),
            font_size=status_font(),
            size_hint=(1, 0.04),
            halign="center",
            valign="middle",
        )
        self.status_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        root.add_widget(self.status_label)

        self.add_widget(root)

    def make_button(self, text, color):
        return Button(
            text=text,
            font_size=max(14, int(button_font() * 0.78)),
            background_normal="",
            background_color=color,
        )

    def media_row_height(self):
        # Compact music rows: we need many songs visible on screen.
        # Keep at least a comfortable button height, but do not use huge global row_height().
        return max(34, int(button_height() * 0.52), int(row_height() * 0.30))

    def media_row_height_for_text(self, display_text):
        base = self.media_row_height()

        # Android wraps long filenames into 2 lines. Give them more height.
        if platform == "android":
            length = len(display_text)

            if length > 70:
                return int(base * 2.15)

            if length > 40:
                return int(base * 1.70)

        return base

    def control_height(self):
        return max(34, int(button_height() * 0.62))

    def small_control_height(self):
        return max(30, int(button_height() * 0.54))

    def search_height(self):
        return max(34, int(input_height() * 0.62))

    def folder_text(self):
        if platform == "android":
            roots = load_storage_roots()
            audio_paths = "\n".join(str(p) for p in audio_folders(self.active_storage)) or "No audio folders found"
            video_paths = "\n".join(str(p) for p in video_folders(self.active_storage)) or "No video folders found"
            download_paths = "\n".join(str(p) for p in download_folders(self.active_storage)) or "No download folders found"

            return (
                f"Storage: {self.active_storage}\n"
                f"Internal root: {roots.get('internal_root', '/storage/emulated/0')}\n"
                f"External root: {roots.get('external_root', '/mnt/sdcard')}\n"
                f"Audio:\n{audio_paths}\n"
                f"Video:\n{video_paths}\n"
                f"Downloads:\n{download_paths}"
            )

        folders = "\n".join(f"{name}: {path}" for name, path in MEDIA_FOLDERS.items())
        return f"Media folders:\n{folders}"

    def on_app_stop(self, *args):
        self.stop_media(None)
        kill_external_players()

    def write_player_status(self, playing=False, filename=""):
        try:
            PLAYER_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
            PLAYER_STATUS_FILE.write_text(
                json.dumps(
                    {
                        "playing": bool(playing),
                        "file": filename or (self.selected_file.name if self.selected_file else ""),
                    },
                    indent=4,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            log.error(f"Music: write player status failed {e}")

    def on_enter(self):
        log.info("Music: opened")
        self.load_favorites()
        self.refresh_media(None)
        Clock.unschedule(self.check_playback_finished)
        Clock.schedule_interval(self.check_playback_finished, 1)

    def on_leave(self):
        # Do NOT stop music when switching to Home, Calendar, Notes, etc.
        # Music should stop only when user presses Stop or when M12 OS exits.
        Clock.unschedule(self.apply_search_filter)

        # Keep Auto Next running while user is on other screens.
        Clock.unschedule(self.check_playback_finished)
        Clock.schedule_interval(self.check_playback_finished, 1)

    def is_video_file(self, path):
        return Path(path).suffix.lower() in VIDEO_EXTENSIONS

    def is_audio_file(self, path):
        return Path(path).suffix.lower() in AUDIO_EXTENSIONS

    def is_existing_media_file(self, path):
        try:
            p = Path(path)
            return p.exists() and p.is_file() and self.is_supported_on_this_platform(p)
        except Exception:
            return False

    def is_supported_on_this_platform(self, path):
        try:
            suffix = Path(path).suffix.lower()
            return suffix in MEDIA_EXTENSIONS
        except Exception:
            return False


    def normalized_path(self, path):
        try:
            return str(Path(path).expanduser().resolve())
        except Exception:
            return str(Path(path))

    def load_favorites(self):
        try:
            if FAVORITES_FILE.exists():
                data = json.loads(FAVORITES_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.favorite_paths = {
                        str(x) for x in data
                        if self.is_existing_media_file(x)
                    }
                    return
        except Exception as e:
            log.error(f"Music: favorites load failed {e}")

        self.favorite_paths = set()

    def save_favorites(self):
        try:
            FAVORITES_FILE.write_text(
                json.dumps(sorted(self.favorite_paths), indent=4),
                encoding="utf-8",
            )
        except Exception as e:
            log.error(f"Music: favorites save failed {e}")

    def set_storage(self, name):
        if platform != "android":
            return

        self.active_storage = name
        self.selected_file = None
        self.update_storage_button_colors()
        self.status_label.text = f"Storage: {self.active_storage}. Scanning..."
        self.refresh_media(None)

    def update_storage_button_colors(self):
        for name, btn in self.storage_buttons.items():
            btn.background_color = (
                (0.10, 0.45, 0.20, 1)
                if name == self.active_storage
                else (0.10, 0.15, 0.25, 1)
            )

    def set_folder(self, name):
        self.active_folder = name
        self.selected_file = None
        self.update_folder_button_colors()
        self.apply_filters()

    def update_folder_button_colors(self):
        for name, btn in self.folder_buttons.items():
            btn.background_color = (
                (0.25, 0.45, 0.75, 1)
                if name == self.active_folder
                else (0.10, 0.15, 0.25, 1)
            )

    def on_search_text_delayed(self, instance, value):
        self.search_text = value.strip().lower()
        Clock.unschedule(self.apply_search_filter)
        Clock.schedule_once(self.apply_search_filter, 0.35)

    def apply_search_filter(self, dt):
        self.apply_filters()

    def clear_search(self, instance):
        Clock.unschedule(self.apply_search_filter)
        self.search_input.text = ""
        self.search_text = ""
        self.apply_filters()

    def scan_folder(self, folder):
        found = []

        try:
            if platform != "android":
                folder.mkdir(parents=True, exist_ok=True)

            if not folder.exists():
                log.warning(f"Music: folder missing {folder}")
                return found

            log.info(f"Music: scanning {folder}")

            for root, dirs, files in os.walk(folder, followlinks=True):
                dirs[:] = [
                    d for d in dirs
                    if d not in (".Trash", ".Trashes", "__MACOSX", ".git")
                ]

                for name in files:
                    self.last_scan_total_files += 1
                    suffix = Path(name).suffix.lower()

                    full_path = Path(root) / name

                    if full_path.exists() and full_path.is_file() and self.is_supported_on_this_platform(full_path):
                        self.last_scan_supported += 1
                        found.append(full_path)
                    else:
                        self.last_scan_unsupported += 1

        except Exception as e:
            self.last_scan_errors += 1
            log.error(f"Music: scan failed {folder}: {e}")

        return found

    def scan_media_files(self):
        self.last_scan_total_files = 0
        self.last_scan_supported = 0
        self.last_scan_unsupported = 0
        self.last_scan_errors = 0

        found = []

        storage = self.active_storage if platform == "android" else "Internal"

        for folder in audio_folders(storage):
            found.extend(self.scan_folder(folder))

        for folder in video_folders(storage):
            found.extend(self.scan_folder(folder))

        for folder in download_folders(storage):
            found.extend(self.scan_folder(folder))

        if platform != "android":
            desktop = Path.home() / "Desktop"

            if desktop.exists():
                found.extend(self.scan_folder(desktop))

        unique = sorted(
            {p for p in found if self.is_existing_media_file(p)},
            key=lambda p: str(p).lower()
        )

        for p in unique[:25]:
            log.info(f"MEDIA FOUND: {p}")

        log.info(
            "Music scan result: "
            f"total={self.last_scan_total_files} "
            f"supported={self.last_scan_supported} "
            f"unique={len(unique)} "
            f"unsupported={self.last_scan_unsupported} "
            f"errors={self.last_scan_errors}"
        )
        log.info("===== AUDIO FOLDERS =====")
        for f in audio_folders():
            log.info(f"AUDIO: {f}")

        log.info("===== VIDEO FOLDERS =====")
        for f in video_folders():
            log.info(f"VIDEO: {f}")

        log.info("===== DOWNLOAD FOLDERS =====")
        for f in download_folders():
            log.info(f"DOWNLOAD: {f}")

        log.info(f"MEDIA FOUND COUNT: {len(unique)}")

        for p in unique[:100]:
            log.info(f"FOUND: {p}")


        return unique

    def refresh_media(self, instance):
        self.status_label.text = "Scanning media files..."
        self.load_favorites()
        self.media_files = self.scan_media_files()

        if self.selected_file and not self.is_existing_media_file(self.selected_file):
            self.selected_file = None

        self.apply_filters()

    def path_is_inside_any(self, path, folders):
        try:
            p_resolved = Path(path).resolve()

            for folder in folders:
                root = Path(folder).resolve()

                if root in p_resolved.parents or p_resolved == root:
                    return True
        except Exception:
            pass

        return False

    def apply_filters(self):
        files = [p for p in self.media_files if self.is_existing_media_file(p)]
        self.media_files = files

        if self.active_folder == "Favorites":
            files = [p for p in files if self.normalized_path(p) in self.favorite_paths]

        elif self.active_folder == "Audio":
            files = [
                p for p in files
                if self.is_audio_file(p)
                and self.path_is_inside_any(p, audio_folders(self.active_storage))
            ]

        elif self.active_folder == "Video":
            files = [
                p for p in files
                if self.is_video_file(p)
                and self.path_is_inside_any(p, video_folders(self.active_storage))
            ]

        elif self.active_folder == "Downloads":
            files = [
                p for p in files
                if self.path_is_inside_any(p, download_folders(self.active_storage))
            ]

        elif self.active_folder != "All":
            folder = MEDIA_FOLDERS.get(self.active_folder)
            if folder:
                files = [
                    p for p in files
                    if self.path_is_inside_any(p, [folder])
                ]

        if self.search_text:
            files = [
                p for p in files
                if self.search_text in p.name.lower()
                or self.search_text in str(p.parent).lower()
            ]

        self.visible_files = files
        self.rebuild_file_list()


    def rebuild_file_list(self):
        self.file_list.clear_widgets()
        self.file_buttons = {}

        if not self.visible_files:
            self.file_list.add_widget(Label(
                text=(
                    f"No files in {self.active_folder}.\n\n"
                    "Try Rescan or clear Search."
                ),
                font_size=text_font(),
                size_hint_y=None,
                height=self.media_row_height() * 2,
                halign="center",
                valign="middle",
            ))
            self.status_label.text = (
                f"Shown: 0 | Total: {len(self.media_files)} | "
                f"Scanned: {self.last_scan_total_files} | "
                f"Unsupported: {self.last_scan_unsupported}"
            )
            return

        for path in self.visible_files:
            is_fav = self.normalized_path(path) in self.favorite_paths
            prefix = "[VIDEO] " if self.is_video_file(path) else "[AUDIO] "
            star = "★ " if is_fav else ""

            display_text = star + prefix + path.name
            row_h = self.media_row_height_for_text(display_text)

            btn = Button(
                text=display_text,
                font_size=max(14, int(text_font() * 0.82)),
                size_hint_y=None,
                height=row_h,
                background_normal="",
                background_color=(0.25, 0.45, 0.75, 1)
                if path == self.selected_file
                else (0.10, 0.15, 0.25, 1),
                halign="left",
                valign="middle",
            )
            btn.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - spacing_size(), val[1] - 4)))
            btn.bind(on_press=lambda inst, p=path: self.select_file(p))
            self.file_buttons[self.normalized_path(path)] = btn
            self.file_list.add_widget(btn)

        self.update_status_count()
        self.scroll_to_selected_later()

    def scroll_to_selected(self):
        if not self.selected_file or not self.visible_files:
            return

        try:
            selected_key = self.normalized_path(self.selected_file)
            index = None

            for i, path in enumerate(self.visible_files):
                if self.normalized_path(path) == selected_key:
                    index = i
                    break

            if index is None:
                return

            total = len(self.visible_files)

            if total <= 1:
                self.song_scroll.scroll_y = 1
                return

            # ScrollView scroll_y: 1 = top, 0 = bottom.
            self.song_scroll.scroll_y = 1 - (index / max(1, total - 1))

        except Exception as e:
            log.error(f"Music: scroll to selected failed {e}")

    def scroll_to_selected_later(self):
        Clock.schedule_once(lambda dt: self.scroll_to_selected(), 0.05)

    def update_status_count(self):
        pos = self.current_index()
        if pos is None:
            playlist_text = f"Shown: {len(self.visible_files)}"
        else:
            playlist_text = f"{pos + 1} / {len(self.visible_files)}"

        self.status_label.text = (
            f"{playlist_text} | "
            f"Total: {len(self.media_files)} | "
            f"Shuffle: {'ON' if self.shuffle_on else 'OFF'} | "
            f"Repeat: {self.repeat_mode}"
        )

    def select_file(self, path):
        if not self.is_existing_media_file(path):
            self.status_label.text = "File no longer exists. Press Rescan."
            self.refresh_media(None)
            return

        old_key = self.normalized_path(self.selected_file) if self.selected_file else None

        self.selected_file = Path(path)
        new_key = self.normalized_path(self.selected_file)

        kind = "Video" if self.is_video_file(path) else "Audio"
        fav = " ★" if new_key in self.favorite_paths else ""

        self.now_label.text = f"Selected {kind}{fav}:\n{self.selected_file.name}"
        self.status_label.text = "Selected. Press Play."

        if old_key and old_key in self.file_buttons:
            self.file_buttons[old_key].background_color = (0.10, 0.15, 0.25, 1)

        if new_key in self.file_buttons:
            self.file_buttons[new_key].background_color = (0.25, 0.45, 0.75, 1)

        self.update_status_count()

    def current_index(self):
        if not self.selected_file:
            return None

        try:
            selected_key = self.normalized_path(self.selected_file)
            for i, path in enumerate(self.visible_files):
                if self.normalized_path(path) == selected_key:
                    return i
        except Exception:
            pass

        return None

    def choose_next_file(self, forward=True, auto=False):
        self.visible_files = [p for p in self.visible_files if self.is_existing_media_file(p)]

        if not self.visible_files:
            return None

        if self.repeat_mode == REPEAT_ONE and auto:
            return self.selected_file

        if self.shuffle_on:
            choices = list(self.visible_files)

            if self.selected_file and len(choices) > 1:
                selected_key = self.normalized_path(self.selected_file)
                choices = [
                    p for p in choices
                    if self.normalized_path(p) != selected_key
                ]

            return random.choice(choices) if choices else self.selected_file

        idx = self.current_index()

        if idx is None:
            return self.visible_files[0]

        if forward:
            next_idx = idx + 1

            if next_idx >= len(self.visible_files):
                if self.repeat_mode == REPEAT_ALL:
                    next_idx = 0
                else:
                    return None

            return self.visible_files[next_idx]

        prev_idx = idx - 1

        if prev_idx < 0:
            if self.repeat_mode == REPEAT_ALL:
                prev_idx = len(self.visible_files) - 1
            else:
                prev_idx = 0

        return self.visible_files[prev_idx]

    def play_next(self, instance=None):
        next_file = self.choose_next_file(forward=True, auto=False)

        if not next_file:
            self.status_label.text = "End of list."
            return

        self.select_file(next_file)
        self.play_selected(None)

    def play_previous(self, instance=None):
        prev_file = self.choose_next_file(forward=False, auto=False)

        if not prev_file:
            self.status_label.text = "No previous file."
            return

        self.select_file(prev_file)
        self.play_selected(None)

    def auto_next(self):
        next_file = self.choose_next_file(forward=True, auto=True)

        if not next_file:
            self.is_playing = False
            self.write_player_status(False)

            self.play_btn.text = "Play"
            self.status_label.text = "Playback finished."
            return

        self.select_file(next_file)
        self.play_selected(None)

    def toggle_shuffle(self, instance):
        self.shuffle_on = not self.shuffle_on
        self.shuffle_btn.text = "Shuffle ON" if self.shuffle_on else "Shuffle OFF"
        self.shuffle_btn.background_color = (
            (0.10, 0.45, 0.20, 1)
            if self.shuffle_on
            else (0.12, 0.20, 0.35, 1)
        )
        self.update_status_count()

    def cycle_repeat(self, instance):
        if self.repeat_mode == REPEAT_OFF:
            self.repeat_mode = REPEAT_ONE
        elif self.repeat_mode == REPEAT_ONE:
            self.repeat_mode = REPEAT_ALL
        else:
            self.repeat_mode = REPEAT_OFF

        self.repeat_btn.text = f"Repeat {self.repeat_mode}"
        self.repeat_btn.background_color = (
            (0.10, 0.45, 0.20, 1)
            if self.repeat_mode != REPEAT_OFF
            else (0.12, 0.20, 0.35, 1)
        )
        self.update_status_count()

    def toggle_favorite(self, instance):
        if not self.selected_file:
            self.status_label.text = "Select a file first."
            return

        key = self.normalized_path(self.selected_file)

        if key in self.favorite_paths:
            self.favorite_paths.remove(key)
            self.status_label.text = "Removed from Favorites"
        else:
            self.favorite_paths.add(key)
            self.status_label.text = "Added to Favorites"

        self.save_favorites()
        self.apply_filters()

    def set_macos_volume(self, value):
        try:
            volume = int(max(0, min(100, value * 100)))
            subprocess.run(
                ["osascript", "-e", f"set volume output volume {volume}"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            log.error(f"Music: mac volume failed {e}")

    def stop_process(self):
        if self.player_process:
            try:
                if self.player_process.poll() is None:
                    if hasattr(os, "killpg"):
                        os.killpg(os.getpgid(self.player_process.pid), signal.SIGTERM)
                    else:
                        self.player_process.terminate()

                    self.player_process.wait(timeout=1)

            except Exception:
                try:
                    self.player_process.kill()
                except Exception:
                    pass

            try:
                if self.player_process in EXTERNAL_PLAYERS:
                    EXTERNAL_PLAYERS.remove(self.player_process)
            except Exception:
                pass

            self.player_process = None

    def stop_android_player(self):
        if self.android_player:
            try:
                try:
                    if self.android_player.isPlaying():
                        self.android_player.stop()
                except Exception:
                    pass
                self.android_player.release()
            except Exception as e:
                log.error(f"Music: Android MediaPlayer stop failed {e}")
            self.android_player = None

    def play_audio_with_android_player(self):
        if autoclass is None:
            self.status_label.text = "Android MediaPlayer API not available."
            return

        try:
            MediaPlayer = autoclass("android.media.MediaPlayer")
            self.android_player = MediaPlayer()
            self.android_player.setDataSource(str(self.selected_file))
            self.android_player.prepare()
            self.android_player.setVolume(float(self.volume_slider.value), float(self.volume_slider.value))
            self.android_player.start()

            self.is_playing = True
            self.write_player_status(True)

            self.play_btn.text = "Play"
            self.now_label.text = f"Playing:\n{self.selected_file.name}"
            self.rebuild_file_list()
            self.update_status_count()
            self.scroll_to_selected_later()
            self.status_label.text = "Playing with Android MediaPlayer"

            log.info(f"Music: Android MediaPlayer playing {self.selected_file}")

        except Exception as e:
            self.status_label.text = f"Android play failed:\n{e}"
            log.error(f"Music: Android MediaPlayer play failed {e}")
            self.stop_android_player()

    def unload_current_sound(self):
        self.stop_process()
        self.stop_android_player()

        if self.sound:
            try:
                self.sound.stop()
                self.sound.unload()
            except Exception as e:
                log.error(f"Music: unload failed {e}")

        self.sound = None

    def play_selected(self, instance):
        if self.is_starting:
            self.status_label.text = "Starting already..."
            return

        if not self.selected_file:
            if self.visible_files:
                self.selected_file = self.visible_files[0]
            else:
                self.status_label.text = "Select a file first."
                return

        if not self.is_existing_media_file(self.selected_file):
            self.status_label.text = "File no longer exists. Press Rescan."
            self.selected_file = None
            self.refresh_media(None)
            return

        self.is_starting = True
        self.play_btn.disabled = True
        self.status_label.text = "Starting..."
        self.now_label.text = f"Starting:\n{self.selected_file.name}"

        Clock.schedule_once(self.do_play_selected, 0.05)

    def do_play_selected(self, dt):
        try:
            self.unload_current_sound()

            if platform == "macosx":
                self.play_with_macos()
                return

            if self.is_video_file(self.selected_file):
                self.open_video_screen()
                return

            if platform == "android":
                self.play_audio_with_android_player()
                return

            self.play_audio_with_kivy()

        finally:
            self.is_starting = False
            self.play_btn.disabled = False

    def open_video_screen(self):
        if not self.selected_file:
            self.status_label.text = "Select video first."
            return

        if platform == "macosx":
            self.play_with_macos()
            return

        if self.manager and self.manager.has_screen("video_player"):
            video_screen = self.manager.get_screen("video_player")

            if hasattr(video_screen, "set_video"):
                video_screen.set_video(str(self.selected_file), return_screen="music")

            self.manager.current = "video_player"
            self.status_label.text = "Opening video screen..."
            return

        self.status_label.text = "Video player screen missing."

    def play_with_macos(self):
        try:
            self.set_macos_volume(self.volume_slider.value)

            if self.is_video_file(self.selected_file):
                subprocess.Popen(
                    ["open", str(self.selected_file)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.now_label.text = f"Opened Video:\n{self.selected_file.name}"
                self.write_player_status(False)
                self.is_playing = False
                self.play_btn.text = "Play"
                self.rebuild_file_list()
                self.update_status_count()
                self.scroll_to_selected_later()
                log.info(f"Music: opened video {self.selected_file.name}")
                return

            popen_kwargs = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }

            if hasattr(os, "setsid"):
                popen_kwargs["preexec_fn"] = os.setsid

            self.player_process = subprocess.Popen(
                ["afplay", str(self.selected_file)],
                **popen_kwargs,
            )
            register_external_player(self.player_process)

            self.is_playing = True
            self.write_player_status(True)

            self.play_btn.text = "Play"
            self.now_label.text = f"Playing Audio:\n{self.selected_file.name}"
            self.rebuild_file_list()
            self.update_status_count()
            self.scroll_to_selected_later()
            log.info(f"Music: afplay {self.selected_file.name}")

        except Exception as e:
            self.status_label.text = f"Play failed:\n{e}"
            log.error(f"Music: mac play failed {e}")

    def play_audio_with_kivy(self):
        try:
            self.sound = SoundLoader.load(str(self.selected_file))

            if not self.sound:
                self.status_label.text = "Could not load this audio file."
                log.error(f"Music: SoundLoader failed for {self.selected_file}")
                return

            self.sound.volume = self.volume_slider.value
            self.sound.play()

            self.is_playing = True
            self.write_player_status(True)

            self.play_btn.text = "Play"
            self.now_label.text = f"Playing:\n{self.selected_file.name}"
            self.rebuild_file_list()
            self.update_status_count()
            self.scroll_to_selected_later()
            log.info(f"Music: playing {self.selected_file.name}")

        except Exception as e:
            self.status_label.text = f"Play failed:\n{e}"
            log.error(f"Music: play failed {e}")

    def check_playback_finished(self, dt):
        if not self.is_playing:
            return

        if platform == "macosx":
            if self.player_process and self.player_process.poll() is not None:
                self.player_process = None
                self.auto_next()
            return

        if platform == "android" and self.android_player:
            try:
                if not self.android_player.isPlaying():
                    self.stop_android_player()
                    self.auto_next()
            except Exception:
                pass
            return

        if self.sound:
            try:
                if self.sound.state == "stop":
                    self.auto_next()
            except Exception:
                pass

    def stop_media(self, instance):
        self.is_playing = False
        self.play_btn.text = "Play"
        self.unload_current_sound()
        self.write_player_status(False)
        self.status_label.text = "Stopped"

    def change_volume(self, instance, value):
        if platform == "macosx":
            self.set_macos_volume(value)
            return

        if platform == "android" and self.android_player:
            try:
                self.android_player.setVolume(float(value), float(value))
                return
            except Exception as e:
                log.error(f"Music: Android volume failed {e}")

        if self.sound:
            try:
                self.sound.volume = value
            except Exception as e:
                log.error(f"Music: volume failed {e}")

    def open_media_folder(self, instance):
        try:
            if platform == "macosx":
                folder = MEDIA_FOLDERS.get(self.active_folder)
                if not folder:
                    folder = MEDIA_FOLDERS.get("Music")
                subprocess.Popen(["open", str(folder)])
            else:
                self.status_label.text = self.folder_text()
        except Exception as e:
            self.status_label.text = f"Open folder failed:\n{e}"

    def go_back(self, instance):
        if self.manager:
            self.manager.current = "home"