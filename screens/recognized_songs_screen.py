from datetime import datetime
import threading
import time
import webbrowser

from kivy.clock import Clock
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.switch import Switch
from kivy.uix.widget import Widget

from services.recognized_music_database import (
    RecognizedMusicDatabase,
)
from utils.logger import log
from utils.system_header import create_system_header
from utils.ui_scale import (
    button_font,
    button_height,
    padding_size,
    spacing_size,
    status_font,
    text_font,
)


YELLOW = (0.82, 0.66, 0.10, 1)
GREEN = (0.10, 0.48, 0.20, 1)
DARK = (0.10, 0.15, 0.25, 1)
RED = (0.48, 0.14, 0.14, 1)
BLUE = (0.12, 0.24, 0.42, 1)
DISABLED = (0.18, 0.18, 0.18, 1)


class SongRowButton(Button):
    """
    One selectable database row.

    Status color remains yellow/green. A selected row gets a white
    outline so selection does not get confused with playback status.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.background_normal = ""
        self.background_down = ""
        self.song_id = ""
        self.song_status = "not_found"

        with self.canvas.after:
            self._selection_color = Color(
                1,
                1,
                1,
                0,
            )
            self._selection_line = Line(
                rectangle=(
                    self.x,
                    self.y,
                    self.width,
                    self.height,
                ),
                width=2.0,
            )

        self.bind(
            pos=self._update_selection_line,
            size=self._update_selection_line,
        )

    def _update_selection_line(
        self,
        *args,
    ):
        self._selection_line.rectangle = (
            self.x,
            self.y,
            self.width,
            self.height,
        )

    def set_selected(
        self,
        selected,
    ):
        self._selection_color.a = (
            1 if selected else 0
        )


class PlaybackActivityIcon(Widget):
    """
    Font-independent modern playback indicator.

    PLAYING:
        Four animated vertical bars.

    PAUSED:
        Two fixed vertical pause bars.

    STOPPED:
        Hidden.
    """

    PLAYING_HEIGHTS = (
        (0.32, 0.72, 1.00, 0.48),
        (0.68, 0.38, 0.76, 1.00),
        (1.00, 0.55, 0.34, 0.72),
        (0.48, 1.00, 0.62, 0.36),
        (0.76, 0.48, 1.00, 0.58),
        (0.42, 0.82, 0.52, 1.00),
    )

    def __init__(
        self,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.mode = "stopped"
        self.phase = 0

        with self.canvas:
            self._bar_color = Color(
                0.20,
                0.82,
                0.48,
                1,
            )

            self._bars = [
                RoundedRectangle(
                    radius=[4],
                )
                for _ in range(4)
            ]

        self.bind(
            pos=self._update_graphics,
            size=self._update_graphics,
        )

        self._update_graphics()

    def set_mode(
        self,
        mode,
    ):
        self.mode = str(
            mode or "stopped"
        ).strip().lower()

        if self.mode not in (
            "playing",
            "paused",
        ):
            self.mode = "stopped"

        self.phase = 0
        self._update_graphics()

    def advance(
        self,
    ):
        if self.mode != "playing":
            return

        self.phase = (
            self.phase + 1
        ) % len(
            self.PLAYING_HEIGHTS
        )

        self._update_graphics()

    def _hide_bars(
        self,
    ):
        for bar in self._bars:
            bar.pos = (
                self.x,
                self.y,
            )
            bar.size = (
                0,
                0,
            )

    def _update_graphics(
        self,
        *args,
    ):
        if (
            self.mode == "stopped"
            or self.width <= 0
            or self.height <= 0
        ):
            self._hide_bars()
            return

        usable_height = max(
            6.0,
            self.height * 0.72,
        )

        center_y = (
            self.y
            + (self.height / 2.0)
        )

        if self.mode == "paused":
            bar_width = max(
                4.0,
                self.width * 0.18,
            )
            gap = max(
                4.0,
                self.width * 0.12,
            )
            total_width = (
                (bar_width * 2.0)
                + gap
            )
            start_x = (
                self.x
                + (
                    self.width
                    - total_width
                ) / 2.0
            )

            for index, bar in enumerate(
                self._bars
            ):
                if index < 2:
                    bar.pos = (
                        start_x
                        + index
                        * (
                            bar_width
                            + gap
                        ),
                        center_y
                        - usable_height
                        / 2.0,
                    )
                    bar.size = (
                        bar_width,
                        usable_height,
                    )
                else:
                    bar.pos = (
                        self.x,
                        self.y,
                    )
                    bar.size = (
                        0,
                        0,
                    )

            return

        heights = self.PLAYING_HEIGHTS[
            self.phase
        ]

        gap = max(
            2.0,
            self.width * 0.055,
        )

        bar_width = max(
            3.0,
            (
                self.width
                - (gap * 3.0)
            ) / 4.0,
        )

        total_width = (
            (bar_width * 4.0)
            + (gap * 3.0)
        )

        start_x = (
            self.x
            + (
                self.width
                - total_width
            ) / 2.0
        )

        for index, bar in enumerate(
            self._bars
        ):
            height = max(
                5.0,
                usable_height
                * heights[index],
            )

            bar.pos = (
                start_x
                + index
                * (
                    bar_width
                    + gap
                ),
                center_y
                - height / 2.0,
            )
            bar.size = (
                bar_width,
                height,
            )


class RecognizedSongsScreen(Screen):
    """
    Pilot UI for the Recognized Songs XML database.

    This stage reads, selects, and deletes database records.
    Streaming search and playback are intentionally not implemented yet.
    """

    def __init__(
        self,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.database = (
            RecognizedMusicDatabase()
        )

        self.songs = []
        self.selected_song = None
        self.playing_song_id = ""
        self.spotify_playback_device_id = ""
        self.spotify_playback_state = "stopped"
        self._playing_animation_event = None
        self._playing_animation_index = 0
        self.row_buttons = {}

        root = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size(),
        )

        self.system_header = create_system_header(
            title="Recognized Songs",
            back_callback=self.go_back,
            status_provider=(
                self.get_system_status_text
            ),
            ai_active=False,
        )
        root.add_widget(
            self.system_header
        )

        self.summary_label = Label(
            text="Recognized songs",
            font_size=text_font(),
            size_hint=(1, None),
            height=max(
                34,
                int(button_height() * 0.55),
            ),
            halign="center",
            valign="middle",
        )
        self.summary_label.bind(
            size=lambda inst, val: setattr(
                inst,
                "text_size",
                val,
            )
        )
        root.add_widget(
            self.summary_label
        )

        self.now_playing_bar = BoxLayout(
            orientation="horizontal",
            spacing=max(
                8,
                spacing_size(),
            ),
            size_hint=(1, None),
            height=0,
            opacity=0,
            padding=(
                max(
                    8,
                    spacing_size(),
                ),
                0,
            ),
        )

        self.playback_activity_icon = (
            PlaybackActivityIcon(
                size_hint=(None, 1),
                width=max(
                    28,
                    int(button_height() * 0.48),
                ),
            )
        )

        self.now_playing_label = Label(
            text="",
            font_size=max(
                14,
                int(text_font() * 0.84),
            ),
            halign="left",
            valign="middle",
        )
        self.now_playing_label.bind(
            size=lambda inst, val: setattr(
                inst,
                "text_size",
                val,
            )
        )

        self.now_playing_bar.add_widget(
            self.playback_activity_icon
        )
        self.now_playing_bar.add_widget(
            self.now_playing_label
        )

        root.add_widget(
            self.now_playing_bar
        )

        self.song_scroll = ScrollView(
            size_hint=(1, 1),
            do_scroll_x=False,
            do_scroll_y=True,
        )

        self.song_list = GridLayout(
            cols=1,
            spacing=spacing_size(),
            size_hint_y=None,
        )
        self.song_list.bind(
            minimum_height=(
                self.song_list.setter("height")
            )
        )

        self.song_scroll.add_widget(
            self.song_list
        )
        root.add_widget(
            self.song_scroll
        )

        controls = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=max(
                38,
                int(button_height() * 0.66),
            ),
        )

        self.delete_btn = self._make_button(
            "Delete",
            RED,
        )
        self.delete_btn.bind(
            on_press=self.delete_selected
        )
        controls.add_widget(
            self.delete_btn
        )

        self.find_btn = self._make_button(
            "Try to Find",
            BLUE,
        )
        self.find_btn.bind(
            on_press=self.try_to_find
        )
        controls.add_widget(
            self.find_btn
        )

        self.play_btn = self._make_button(
            "Play",
            GREEN,
        )
        self.play_btn.bind(
            on_press=self.play_selected
        )
        controls.add_widget(
            self.play_btn
        )

        self.pause_btn = self._make_button(
            "Pause",
            BLUE,
        )
        self.pause_btn.bind(
            on_press=self.pause_selected
        )
        controls.add_widget(
            self.pause_btn
        )

        self.stop_btn = self._make_button(
            "Stop",
            RED,
        )
        self.stop_btn.bind(
            on_press=self.stop_selected
        )
        controls.add_widget(
            self.stop_btn
        )

        root.add_widget(
            controls
        )

        browser_row = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=max(
                34,
                int(button_height() * 0.55),
            ),
        )

        browser_label = Label(
            text="Play in Browser",
            font_size=status_font(),
            size_hint=(0.78, 1),
            halign="right",
            valign="middle",
        )
        browser_label.bind(
            size=lambda inst, val: setattr(
                inst,
                "text_size",
                val,
            )
        )

        self.play_in_browser_switch = Switch(
            active=False,
            size_hint=(0.22, 1),
        )

        browser_row.add_widget(
            browser_label
        )
        browser_row.add_widget(
            self.play_in_browser_switch
        )

        root.add_widget(
            browser_row
        )

        self.status_label = Label(
            text="",
            font_size=status_font(),
            size_hint=(1, None),
            height=max(
                52,
                int(button_height() * 0.82),
            ),
            halign="center",
            valign="middle",
        )
        self.status_label.bind(
            size=lambda inst, val: setattr(
                inst,
                "text_size",
                (
                    val[0],
                    None,
                ),
            )
        )
        self.status_label.bind(
            texture_size=lambda inst, val: setattr(
                inst,
                "height",
                max(
                    52,
                    min(
                        104,
                        int(val[1] + 10),
                    ),
                ),
            )
        )
        root.add_widget(
            self.status_label
        )

        self.add_widget(root)

        self._update_buttons()

    def _make_button(
        self,
        text,
        color,
    ):
        return Button(
            text=text,
            font_size=max(
                14,
                int(button_font() * 0.76),
            ),
            background_normal="",
            background_down="",
            background_color=color,
        )

    def on_enter(self):
        self.refresh_songs()

    def refresh_songs(self):
        try:
            self.songs = (
                self.database.list_songs()
            )
        except Exception as error:
            self.songs = []
            self.status_label.text = (
                "Could not read recognized songs: "
                f"{error}"
            )
            log.error(
                "RecognizedSongs: database read failed "
                f"{type(error).__name__}: {error}"
            )

        selected_id = ""

        if self.selected_song:
            selected_id = str(
                self.selected_song.get(
                    "id",
                    "",
                )
            ).strip()

        self.song_list.clear_widgets()
        self.row_buttons = {}
        self.selected_song = None

        if not self.songs:
            empty = Label(
                text="No recognized songs yet.",
                font_size=text_font(),
                size_hint_y=None,
                height=max(
                    80,
                    int(button_height() * 1.3),
                ),
                halign="center",
                valign="middle",
            )
            empty.bind(
                size=lambda inst, val: setattr(
                    inst,
                    "text_size",
                    val,
                )
            )
            self.song_list.add_widget(
                empty
            )

            self.summary_label.text = (
                "Recognized songs: 0"
            )
            self.status_label.text = (
                "Recognize a song to add it here."
            )
            self._update_buttons()
            return

        for song in self.songs:
            row = self._build_song_row(
                song
            )
            self.song_list.add_widget(
                row
            )

            song_id = str(
                song.get("id", "")
            ).strip()

            self.row_buttons[
                song_id
            ] = row

            if (
                selected_id
                and song_id == selected_id
            ):
                self.selected_song = song
                row.set_selected(True)

        self.summary_label.text = (
            f"Recognized songs: "
            f"{len(self.songs)}"
        )

        if self.selected_song:
            self.status_label.text = (
                "Selected: "
                + self._song_name(
                    self.selected_song
                )
            )
        else:
            self.status_label.text = (
                "Select one record."
            )

        self._update_buttons()

    def _build_song_row(
        self,
        song,
    ):
        status = str(
            song.get(
                "status",
                "not_found",
            )
        ).strip().lower()

        found = (
            status == "found"
            and bool(
                str(
                    song.get(
                        "play_url",
                        "",
                    )
                ).strip()
            )
        )

        row_color = (
            GREEN if found else YELLOW
        )

        text_color = (
            (1, 1, 1, 1)
            if found
            else (0.05, 0.05, 0.05, 1)
        )

        display_status = (
            "FOUND"
            if found
            else "NOT FOUND"
        )

        link = str(
            song.get(
                "play_url",
                "",
            )
        ).strip() or "—"

        display_text = (
            f"{song.get('title', '')}\n"
            f"Artist: {song.get('artist', '')}\n"
            f"Album: "
            f"{song.get('album', '') or '—'}\n"
            f"Recognized: "
            f"{self._format_date(song.get('recognized_at', ''))}\n"
            f"Recognition: "
            f"{song.get('recognition_provider', '') or '—'}"
            f"   |   Status: {display_status}\n"
            f"Playback: "
            f"{song.get('playback_provider', '') or 'amazon_music'}"
            f"   |   Link: {link}"
        )

        row = SongRowButton(
            text=display_text,
            font_size=max(
                13,
                int(text_font() * 0.72),
            ),
            size_hint_y=None,
            height=max(
                122,
                int(
                    button_height()
                    * 2.05
                ),
            ),
            background_color=row_color,
            color=text_color,
            halign="left",
            valign="middle",
            padding=(
                spacing_size(),
                max(
                    4,
                    int(spacing_size() * 0.45),
                ),
            ),
        )

        row.song_id = str(
            song.get("id", "")
        ).strip()
        row.song_status = status

        row.bind(
            size=lambda inst, val: setattr(
                inst,
                "text_size",
                (
                    val[0]
                    - (spacing_size() * 2),
                    val[1] - 8,
                ),
            )
        )

        row.bind(
            on_press=lambda inst, item=song: (
                self.select_song(
                    item
                )
            )
        )

        return row

    @staticmethod
    def _song_name(
        song,
    ):
        title = str(
            song.get("title", "")
        ).strip()
        artist = str(
            song.get("artist", "")
        ).strip()

        if title and artist:
            return f"{title} — {artist}"

        return title or artist or "Song"

    @staticmethod
    def _format_date(
        value,
    ):
        raw = str(
            value or ""
        ).strip()

        if not raw:
            return "—"

        try:
            parsed = datetime.fromisoformat(
                raw
            )
            return parsed.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except Exception:
            return raw

    def select_song(
        self,
        song,
    ):
        old_id = ""

        if self.selected_song:
            old_id = str(
                self.selected_song.get(
                    "id",
                    "",
                )
            ).strip()

        if (
            old_id
            and old_id in self.row_buttons
        ):
            self.row_buttons[
                old_id
            ].set_selected(False)

        self.selected_song = song

        new_id = str(
            song.get("id", "")
        ).strip()

        if new_id in self.row_buttons:
            self.row_buttons[
                new_id
            ].set_selected(True)

        self.status_label.text = (
            "Selected: "
            + self._song_name(song)
        )

        self._update_buttons()

    def _selected_is_found(
        self,
    ):
        if not self.selected_song:
            return False

        status = str(
            self.selected_song.get(
                "status",
                "",
            )
        ).strip().lower()

        play_url = str(
            self.selected_song.get(
                "play_url",
                "",
            )
        ).strip()

        return (
            status == "found"
            and bool(play_url)
        )

    def _update_buttons(
        self,
    ):
        selected = (
            self.selected_song is not None
        )

        found = (
            self._selected_is_found()
            if selected
            else False
        )

        playing = (
            self.spotify_playback_state
            == "playing"
            and bool(
                self.playing_song_id
            )
        )

        paused = (
            self.spotify_playback_state
            == "paused"
            and bool(
                self.playing_song_id
            )
        )

        self.delete_btn.disabled = (
            not selected
        )

        self.find_btn.disabled = (
            not selected
            or found
        )

        self.play_btn.disabled = (
            not selected
            or not found
        )

        self.pause_btn.disabled = (
            not playing
        )

        self.stop_btn.disabled = (
            not (
                playing
                or paused
            )
        )

        self.delete_btn.background_color = (
            RED if selected else DISABLED
        )

        self.find_btn.background_color = (
            BLUE
            if selected and not found
            else DISABLED
        )

        self.play_btn.background_color = (
            GREEN
            if selected and found
            else DISABLED
        )

        self.pause_btn.background_color = (
            BLUE
            if playing
            else DISABLED
        )

        self.stop_btn.background_color = (
            RED
            if playing or paused
            else DISABLED
        )

    def delete_selected(
        self,
        instance=None,
    ):
        if not self.selected_song:
            return

        song = dict(
            self.selected_song
        )

        content = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size(),
        )

        message = Label(
            text=(
                "Delete this recognized song?\n\n"
                + self._song_name(song)
            ),
            font_size=text_font(),
            halign="center",
            valign="middle",
        )
        message.bind(
            size=lambda inst, val: setattr(
                inst,
                "text_size",
                val,
            )
        )
        content.add_widget(message)

        buttons = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=max(
                40,
                int(button_height() * 0.70),
            ),
        )

        yes_btn = self._make_button(
            "YES",
            RED,
        )

        cancel_btn = self._make_button(
            "CANCEL",
            DARK,
        )

        buttons.add_widget(
            yes_btn
        )
        buttons.add_widget(
            cancel_btn
        )
        content.add_widget(
            buttons
        )

        popup = Popup(
            title="Confirm Delete",
            content=content,
            size_hint=(0.78, 0.42),
            auto_dismiss=False,
        )

        yes_btn.bind(
            on_press=lambda btn: (
                self._confirm_delete(
                    song,
                    popup,
                )
            )
        )

        cancel_btn.bind(
            on_press=lambda btn: (
                popup.dismiss()
            )
        )

        popup.open()

    def _confirm_delete(
        self,
        song,
        popup,
    ):
        song_id = str(
            song.get("id", "")
        ).strip()

        try:
            deleted = (
                self.database.delete_song(
                    song_id
                )
            )

            popup.dismiss()

            if deleted:
                name = self._song_name(
                    song
                )

                self.selected_song = None
                self.refresh_songs()
                self.status_label.text = (
                    f"Deleted: {name}"
                )
            else:
                self.status_label.text = (
                    "The selected song was "
                    "not found in the database."
                )

        except Exception as error:
            popup.dismiss()
            self.status_label.text = (
                "Delete failed: "
                f"{error}"
            )
            log.error(
                "RecognizedSongs: delete failed "
                f"{type(error).__name__}: {error}"
            )

    def try_to_find(
        self,
        instance=None,
    ):
        """
        Search Spotify for the selected yellow record.

        A confident Spotify match is saved into the existing XML playback
        fields and immediately turns the record green. A weak/no match leaves
        the database unchanged.
        """
        if not self.selected_song:
            return

        if self._selected_is_found():
            self.status_label.text = (
                "This song already has a "
                "playback link."
            )
            return

        title = str(
            self.selected_song.get(
                "title",
                "",
            )
        ).strip()

        artist = str(
            self.selected_song.get(
                "artist",
                "",
            )
        ).strip()

        album = str(
            self.selected_song.get(
                "album",
                "",
            )
        ).strip()

        song_id = str(
            self.selected_song.get(
                "id",
                "",
            )
        ).strip()

        if not title and not artist:
            self.status_label.text = (
                "This record has no title "
                "or artist to search."
            )
            return

        if not song_id:
            self.status_label.text = (
                "This record has no database ID."
            )
            return

        self.find_btn.disabled = True
        self.status_label.text = (
            "Searching Spotify for: "
            + self._song_name(
                self.selected_song
            )
        )

        worker = threading.Thread(
            target=self._spotify_find_worker,
            args=(
                song_id,
                title,
                artist,
                album,
            ),
            daemon=True,
            name="M12SpotifyFind",
        )
        worker.start()

    def _spotify_find_worker(
        self,
        song_id,
        title,
        artist,
        album,
    ):
        try:
            from services.spotify_music_service import (
                spotify_music_service,
            )

            result = (
                spotify_music_service
                .find_track(
                    title=title,
                    artist=artist,
                    album=album,
                )
            )

            Clock.schedule_once(
                lambda dt: (
                    self._spotify_find_finished(
                        song_id,
                        result,
                    )
                ),
                0,
            )

        except Exception as error:
            message = (
                f"{type(error).__name__}: "
                f"{error}"
            )

            Clock.schedule_once(
                lambda dt: (
                    self._spotify_find_failed(
                        message
                    )
                ),
                0,
            )

    def _spotify_find_finished(
        self,
        song_id,
        result,
    ):
        if not result:
            self.status_label.text = (
                "No confident Spotify match found. "
                "Song remains yellow."
            )
            self._update_buttons()
            return

        try:
            updated_song = (
                self.database
                .mark_playback_found(
                    song_id=song_id,
                    play_url=result.get(
                        "play_url",
                        "",
                    ),
                    provider="spotify",
                    track_id=result.get(
                        "track_id",
                        "",
                    ),
                )
            )

            if not updated_song:
                self.status_label.text = (
                    "Spotify match was found, but "
                    "the database record could not "
                    "be updated."
                )
                self._update_buttons()
                return

            self.selected_song = (
                updated_song
            )
            self.refresh_songs()

            score = float(
                result.get(
                    "score",
                    0.0,
                )
            )

            self.status_label.text = (
                "Spotify found: "
                f"{result.get('artist', '')} — "
                f"{result.get('title', '')} "
                f"({score:.0%} match)"
            )

            log.info(
                "RecognizedSongs: Spotify match "
                f"saved track_id="
                f"{result.get('track_id', '')} "
                f"score={score:.3f}"
            )

        except Exception as error:
            self._spotify_find_failed(
                f"{type(error).__name__}: "
                f"{error}"
            )

    def _spotify_find_failed(
        self,
        message,
    ):
        self.status_label.text = (
            "Spotify search failed: "
            + str(message)
        )

        log.error(
            "RecognizedSongs: Spotify search "
            "failed "
            + str(message)
        )

        self._update_buttons()

    def _find_song_by_id(
        self,
        song_id,
    ):
        wanted = str(
            song_id or ""
        ).strip()

        if not wanted:
            return None

        for song in self.songs:
            if str(
                song.get(
                    "id",
                    "",
                )
            ).strip() == wanted:
                return song

        return None

    def _update_now_playing_bar(
        self,
    ):
        if (
            self.spotify_playback_state
            == "playing"
            and self.playing_song_id
        ):
            song = self._find_song_by_id(
                self.playing_song_id
            )

            song_name = (
                self._song_name(song)
                if song
                else "Spotify"
            )

            self.now_playing_label.text = (
                "PLAYING NOW  -  "
                + song_name
            )

            self.now_playing_bar.height = max(
                42,
                int(button_height() * 0.72),
            )
            self.now_playing_bar.opacity = 1

            self.playback_activity_icon.set_mode(
                "playing"
            )
            return

        if (
            self.spotify_playback_state
            == "paused"
            and self.playing_song_id
        ):
            song = self._find_song_by_id(
                self.playing_song_id
            )

            song_name = (
                self._song_name(song)
                if song
                else "Spotify"
            )

            self.now_playing_label.text = (
                "PAUSED  -  "
                + song_name
            )

            self.now_playing_bar.height = max(
                42,
                int(button_height() * 0.72),
            )
            self.now_playing_bar.opacity = 1

            self.playback_activity_icon.set_mode(
                "paused"
            )
            return

        self.playback_activity_icon.set_mode(
            "stopped"
        )
        self.now_playing_label.text = ""
        self.now_playing_bar.height = 0
        self.now_playing_bar.opacity = 0

    def _start_playing_animation(
        self,
    ):
        self._stop_playing_animation()
        self._playing_animation_index = 0
        self._update_now_playing_bar()

        self._playing_animation_event = (
            Clock.schedule_interval(
                self._animate_playing_row,
                0.22,
            )
        )

    def _stop_playing_animation(
        self,
    ):
        if self._playing_animation_event is not None:
            try:
                self._playing_animation_event.cancel()
            except Exception:
                pass

        self._playing_animation_event = None

    def _refresh_current_track_row(
        self,
    ):
        current_id = self.playing_song_id

        self.refresh_songs()

        if current_id:
            for song in self.songs:
                if str(
                    song.get(
                        "id",
                        "",
                    )
                ).strip() == current_id:
                    self.select_song(song)
                    break

        self._update_now_playing_bar()

    def _animate_playing_row(
        self,
        dt,
    ):
        if (
            self.spotify_playback_state
            != "playing"
        ):
            self._stop_playing_animation()
            self._update_now_playing_bar()
            return False

        self._playing_animation_index = (
            self._playing_animation_index + 1
        ) % 6

        self.playback_activity_icon.advance()
        return True

    def play_selected(
        self,
        instance=None,
    ):
        """
        Play the selected green song.

        Default:
            Spotify Connect exact-track playback.

        Optional:
            When Play in Browser is ON, open the saved playback URL.
        """
        if not self._selected_is_found():
            self.status_label.text = (
                "This song has no valid "
                "playback link."
            )
            return

        provider = str(
            self.selected_song.get(
                "playback_provider",
                "",
            )
        ).strip().lower()

        selected_id = str(
            self.selected_song.get(
                "id",
                "",
            )
        ).strip()

        # Resume must be checked BEFORE the browser switch.
        # Otherwise PLAY after PAUSE opens a new browser tab and
        # restarts the track from the beginning.
        if (
            self.spotify_playback_state
            == "paused"
            and selected_id
            and selected_id
            == self.playing_song_id
        ):
            self.play_btn.disabled = True
            self.status_label.text = (
                "Resuming Spotify..."
            )

            threading.Thread(
                target=self._spotify_resume_worker,
                daemon=True,
                name="M12SpotifyResume",
            ).start()
            return

        if bool(
            self.play_in_browser_switch.active
        ):
            self._play_selected_in_browser()
            return

        if provider != "spotify":
            self.status_label.text = (
                "Direct playback is available "
                "for Spotify songs. Turn on "
                "Play in Browser for this link."
            )
            return

        track_id = str(
            self.selected_song.get(
                "track_id",
                "",
            )
        ).strip()

        if not track_id:
            self.status_label.text = (
                "This Spotify song has no "
                "saved track ID."
            )
            return

        self.play_btn.disabled = True
        self.status_label.text = (
            "Starting Spotify: "
            + self._song_name(
                self.selected_song
            )
        )

        worker = threading.Thread(
            target=self._spotify_play_worker,
            args=(track_id,),
            daemon=True,
            name="M12SpotifyPlay",
        )
        worker.start()

    def _spotify_play_worker(
        self,
        track_id,
    ):
        try:
            from services.spotify_music_service import (
                spotify_music_service,
            )

            result = (
                spotify_music_service
                .play_track(
                    track_id
                )
            )

            Clock.schedule_once(
                lambda dt: (
                    self._spotify_play_finished(
                        result
                    )
                ),
                0,
            )

        except Exception as error:
            message = (
                f"{type(error).__name__}: "
                f"{error}"
            )

            Clock.schedule_once(
                lambda dt: (
                    self._spotify_play_failed(
                        message
                    )
                ),
                0,
            )

    def _spotify_play_finished(
        self,
        result,
    ):
        device_name = str(
            result.get(
                "device_name",
                "",
            )
        ).strip()

        self.spotify_playback_device_id = str(
            result.get(
                "device_id",
                "",
            )
        ).strip()

        if self.selected_song:
            self.playing_song_id = str(
                self.selected_song.get(
                    "id",
                    "",
                )
            ).strip()

        self.spotify_playback_state = (
            "playing"
        )
        self._start_playing_animation()
        self._refresh_current_track_row()

        if device_name:
            self.status_label.text = (
                "Playing on Spotify device: "
                + device_name
            )
        else:
            self.status_label.text = (
                "Playing exact Spotify track."
            )

        log.info(
            "RecognizedSongs: Spotify exact "
            "track started "
            f"track_id="
            f"{result.get('track_id', '')} "
            f"device="
            f"{device_name}"
        )

        self._update_buttons()

    def _spotify_play_failed(
        self,
        message,
    ):
        self.status_label.text = (
            "Spotify playback failed: "
            + str(message)
        )

        log.error(
            "RecognizedSongs: Spotify playback "
            "failed "
            + str(message)
        )

        self._update_buttons()

    def _spotify_resume_worker(
        self,
    ):
        try:
            from services.spotify_music_service import (
                spotify_music_service,
            )

            result = (
                spotify_music_service
                .resume_playback(
                    device_id=(
                        self.spotify_playback_device_id
                    )
                )
            )

            Clock.schedule_once(
                lambda dt: (
                    self._spotify_resume_finished(
                        result
                    )
                ),
                0,
            )

        except Exception as error:
            message = (
                f"{type(error).__name__}: "
                f"{error}"
            )

            Clock.schedule_once(
                lambda dt: (
                    self._spotify_resume_failed(
                        message
                    )
                ),
                0,
            )

    def _spotify_resume_finished(
        self,
        result,
    ):
        self.spotify_playback_state = (
            "playing"
        )
        self._start_playing_animation()
        self._refresh_current_track_row()

        device_name = str(
            result.get(
                "device_name",
                "",
            )
        ).strip()

        self.status_label.text = (
            "Spotify resumed"
            + (
                f" on {device_name}"
                if device_name
                else ""
            )
            + "."
        )

        self._update_buttons()

    def _spotify_resume_failed(
        self,
        message,
    ):
        self.status_label.text = (
            "Spotify resume failed: "
            + str(message)
        )

        log.error(
            "RecognizedSongs: Spotify resume "
            "failed "
            + str(message)
        )

        self._update_buttons()

    def pause_selected(
        self,
        instance=None,
    ):
        if (
            self.spotify_playback_state
            != "playing"
        ):
            return

        self.pause_btn.disabled = True
        self.status_label.text = (
            "Pausing Spotify..."
        )

        threading.Thread(
            target=self._spotify_pause_worker,
            args=(False,),
            daemon=True,
            name="M12SpotifyPause",
        ).start()

    def stop_selected(
        self,
        instance=None,
    ):
        if self.spotify_playback_state not in (
            "playing",
            "paused",
        ):
            return

        # If Spotify is already paused, STOP should not send another
        # pause command. Spotify can reject that redundant command.
        # Just clear M12's current-track state so the next PLAY starts
        # the selected track from the beginning.
        if (
            self.spotify_playback_state
            == "paused"
        ):
            self._stop_playing_animation()
            self.spotify_playback_state = (
                "stopped"
            )
            self.playing_song_id = ""
            self.spotify_playback_device_id = ""
            self.refresh_songs()
            self._update_now_playing_bar()
            self.status_label.text = (
                "Spotify stopped."
            )
            self._update_buttons()
            return

        self.stop_btn.disabled = True
        self.status_label.text = (
            "Stopping Spotify..."
        )

        threading.Thread(
            target=self._spotify_pause_worker,
            args=(True,),
            daemon=True,
            name="M12SpotifyStop",
        ).start()

    def _spotify_pause_worker(
        self,
        clear_playing,
    ):
        try:
            from services.spotify_music_service import (
                spotify_music_service,
            )

            result = (
                spotify_music_service
                .pause_playback(
                    device_id=(
                        self.spotify_playback_device_id
                    )
                )
            )

            Clock.schedule_once(
                lambda dt: (
                    self._spotify_pause_finished(
                        result,
                        clear_playing,
                    )
                ),
                0,
            )

        except Exception as error:
            message = (
                f"{type(error).__name__}: "
                f"{error}"
            )

            Clock.schedule_once(
                lambda dt: (
                    self._spotify_pause_failed(
                        message
                    )
                ),
                0,
            )

    def _spotify_pause_finished(
        self,
        result,
        clear_playing,
    ):
        self._stop_playing_animation()

        if clear_playing:
            self.spotify_playback_state = (
                "stopped"
            )
            self.playing_song_id = ""
            self.spotify_playback_device_id = ""
            self.refresh_songs()
            self._update_now_playing_bar()
            self.status_label.text = (
                "Spotify stopped."
            )
        else:
            self.spotify_playback_state = (
                "paused"
            )
            self._refresh_current_track_row()
            self._update_now_playing_bar()
            self.status_label.text = (
                "Spotify paused."
            )

        self._update_buttons()

    def _spotify_pause_failed(
        self,
        message,
    ):
        self.status_label.text = (
            "Spotify control failed: "
            + str(message)
        )

        log.error(
            "RecognizedSongs: Spotify control "
            "failed "
            + str(message)
        )

        self._update_buttons()

    def _play_selected_in_browser(
        self,
    ):
        play_url = str(
            self.selected_song.get(
                "play_url",
                "",
            )
        ).strip()

        track_id = str(
            self.selected_song.get(
                "track_id",
                "",
            )
        ).strip()

        provider = str(
            self.selected_song.get(
                "playback_provider",
                "",
            )
        ).strip().lower()

        if not play_url:
            self.status_label.text = (
                "This song has no saved "
                "playback URL."
            )
            return

        if (
            provider != "spotify"
            or not track_id
        ):
            try:
                opened = webbrowser.open(
                    play_url,
                    new=2,
                )

                if opened is False:
                    raise RuntimeError(
                        "The system browser did not "
                        "accept the playback URL."
                    )

                self.status_label.text = (
                    "Opening in browser: "
                    + self._song_name(
                        self.selected_song
                    )
                )

            except Exception as error:
                self.status_label.text = (
                    "Could not open playback link: "
                    f"{error}"
                )
            return

        self.play_btn.disabled = True
        self.status_label.text = (
            "Opening Spotify Web Player..."
        )

        song_id = str(
            self.selected_song.get(
                "id",
                "",
            )
        ).strip()

        threading.Thread(
            target=self._spotify_browser_worker,
            args=(
                play_url,
                track_id,
                song_id,
            ),
            daemon=True,
            name="M12SpotifyBrowserPlayback",
        ).start()

    def _spotify_browser_worker(
        self,
        play_url,
        track_id,
        song_id,
    ):
        try:
            from services.spotify_music_service import (
                spotify_music_service,
            )

            before_devices = (
                spotify_music_service
                .available_devices()
            )

            before_ids = {
                str(
                    device.get(
                        "id",
                        "",
                    )
                ).strip()
                for device in before_devices
                if str(
                    device.get(
                        "id",
                        "",
                    )
                ).strip()
            }

            opened = webbrowser.open(
                play_url,
                new=2,
            )

            if opened is False:
                raise RuntimeError(
                    "The system browser did not "
                    "accept the playback URL."
                )

            # The Spotify Web Player can already be present in the
            # Connect device list before this button is pressed. In that
            # case waiting only for a brand-new device incorrectly times
            # out even though the browser is already playing.
            #
            # After opening the Web Player, prefer the active controllable
            # Spotify device. If no device is active yet, keep waiting for
            # a newly registered device as the secondary path.
            browser_device = None
            deadline = time.monotonic() + 15.0

            while time.monotonic() < deadline:
                devices = (
                    spotify_music_service
                    .available_devices()
                )

                active_devices = [
                    device
                    for device in devices
                    if str(
                        device.get(
                            "id",
                            "",
                        )
                    ).strip()
                    and not bool(
                        device.get(
                            "is_restricted"
                        )
                    )
                    and bool(
                        device.get(
                            "is_active"
                        )
                    )
                ]

                if active_devices:
                    browser_device = active_devices[0]
                    break

                for device in devices:
                    device_id = str(
                        device.get(
                            "id",
                            "",
                        )
                    ).strip()

                    if (
                        device_id
                        and device_id not in before_ids
                        and not bool(
                            device.get(
                                "is_restricted"
                            )
                        )
                    ):
                        browser_device = device
                        break

                if browser_device is not None:
                    break

                time.sleep(1.0)

            if browser_device is None:
                raise RuntimeError(
                    "Spotify Web Player opened, "
                    "but no controllable Spotify "
                    "Connect device became active. "
                    "Make sure you are signed in "
                    "to Spotify in the browser."
                )

            device_id = str(
                browser_device.get(
                    "id",
                    "",
                )
            ).strip()

            result = (
                spotify_music_service
                .play_track_on_device(
                    track_id,
                    device_id,
                )
            )

            Clock.schedule_once(
                lambda dt: (
                    self._spotify_browser_finished(
                        result,
                        song_id,
                    )
                ),
                0,
            )

        except Exception as error:
            message = (
                f"{type(error).__name__}: "
                f"{error}"
            )

            Clock.schedule_once(
                lambda dt: (
                    self._spotify_browser_failed(
                        message
                    )
                ),
                0,
            )

    def _spotify_browser_finished(
        self,
        result,
        song_id,
    ):
        self.playing_song_id = str(
            song_id or ""
        ).strip()

        self.spotify_playback_device_id = str(
            result.get(
                "device_id",
                "",
            )
        ).strip()

        self.spotify_playback_state = (
            "playing"
        )

        self._start_playing_animation()
        self._refresh_current_track_row()

        device_name = str(
            result.get(
                "device_name",
                "",
            )
        ).strip()

        self.status_label.text = (
            "Playing in browser"
            + (
                f" on {device_name}"
                if device_name
                else ""
            )
            + "."
        )

        log.info(
            "RecognizedSongs: Spotify browser "
            "exact track started "
            f"track_id={result.get('track_id', '')} "
            f"device={device_name}"
        )

        self._update_buttons()

    def _spotify_browser_failed(
        self,
        message,
    ):
        self.status_label.text = (
            "Spotify browser playback failed: "
            + str(message)
        )

        log.error(
            "RecognizedSongs: Spotify browser "
            "playback failed "
            + str(message)
        )

        self._update_buttons()

    def get_system_status_text(
        self,
    ):
        if (
            self.manager
            and self.manager.has_screen("home")
        ):
            home = self.manager.get_screen(
                "home"
            )

            provider = getattr(
                home,
                "get_system_status_text",
                None,
            )

            if callable(provider):
                return provider()

        return "WiFi"

    def go_back(
        self,
        instance=None,
    ):
        if self.manager:
            self.manager.current = "music"