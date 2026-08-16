import json
import base64
import queue
import re
import threading
import subprocess
import sys
import ssl
import urllib.parse
import urllib.request
import webbrowser
from kivy.utils import platform
from datetime import datetime
from pathlib import Path

import certifi

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.utils import escape_markup

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.image import AsyncImage
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from services.ai_actions import AIActions
from services.ai_router import AIRouter
from services.ai_session_memory import get_ai_session_memory
from services.realtime_voice_service import RealtimeVoiceService
from services.voice_service import VoiceService
from utils.system_header import create_system_header
from utils.ui_scale import font, height, device_profile

BASE_DIR = Path(__file__).resolve().parent.parent
AI_SETTINGS_FILE = BASE_DIR / "config" / "ai_settings.json"
AI_CONVERSATION_FILE = BASE_DIR / "data" / "ai" / "conversation_history.txt"

VOICE_LANGUAGES = (
    ("en", "English"),
    ("ru", "Russian"),
    ("auto", "Auto"),
)



class AIScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.return_screen = "home"

        # Keep one router alive so AI conversation memory remains.
        self.ai_router = AIRouter()

        # Voice service is created only when it is first needed.
        self.voice_service = None
        self.realtime_voice_service = None
        self.realtime_voice_active = False
        self.realtime_answer_active = False
        self.realtime_answer_text = ""
        self.realtime_local_speech_active = False
        self.session_memory = get_ai_session_memory()

        self.voice_is_busy = False
        self.ai_is_busy = False
        self.continuous_voice = False
        self.setting_voice_text = False
        self.speech_is_busy = False

        # Streaming answer and speech-queue state.
        self.streaming_answer = ""
        self.streaming_spoken_length = 0
        self.speech_queue = None

        # Throttle chat redraws so the selectable TextInput does not flicker
        # while streaming many small AI deltas.
        self._chat_refresh_event = None
        self._chat_refresh_pending = False
        self._chat_auto_follow = True
        self._log_auto_follow = True
        self._conversation_save_event = None

        # AI Mode is the default. In AI Mode every message goes to AI.
        # Control Mode is used only for M12 application commands.
        self.control_mode = False
        self.navigation_history = []

        # Full-screen System Log state. Existing status assignments are
        # captured automatically through the voice_status text binding.
        self.system_log_lines = []
        self._last_system_status = ""
        self._system_log_limit = 100

        self.voice_language = (
            self.load_voice_language()
        )

        self.chat_text = self.load_conversation_history()

        # ImageSkill popup-gallery state.
        # Images are shown in a popup so Conversation/System Log sizing
        # remains exactly the same as the stable AI screen.
        self.current_image_items = []
        self.current_image_query = ""

        profile = device_profile()

        # ---------------------------------------------------------
        # Responsive AI layout
        # ---------------------------------------------------------
        # Keep all AI/voice logic identical; only widget sizing changes here.
        # These values are deliberately denser than the original AI screen so
        # Conversation remains the main area and controls never overlap.
        if profile == "phone":
            screen_padding = 12
            screen_spacing = 7
            title_hint = 0.055
            mode_hint = 0.065
            section_title_hint = 0.030
            chat_hint = 0.365
            input_hint = 0.105
            message_buttons_hint = 0.070
            log_hint = 0.105
            log_buttons_hint = 0.060
            back_hint = 0.055

            title_size = 26
            mode_size = 16
            section_size = 14
            chat_size = 22
            input_size = 18
            message_button_size = 14
            log_size = 16
            log_button_size = 13
            back_size = 16

        elif profile == "tablet":
            screen_padding = 12
            screen_spacing = 8
            title_hint = 0.060
            mode_hint = 0.070
            section_title_hint = 0.032
            chat_hint = 0.355
            input_hint = 0.110
            message_buttons_hint = 0.072
            log_hint = 0.110
            log_buttons_hint = 0.060
            back_hint = 0.055

            title_size = 24
            mode_size = 16
            section_size = 14
            chat_size = 18
            input_size = 18
            message_button_size = 14
            log_size = 12
            log_button_size = 13
            back_size = 16

        elif profile == "m12":
            screen_padding = 10
            screen_spacing = 7
            title_hint = 0.060
            mode_hint = 0.070
            section_title_hint = 0.032
            chat_hint = 0.350
            input_hint = 0.115
            message_buttons_hint = 0.075
            log_hint = 0.105
            log_buttons_hint = 0.060
            back_hint = 0.055

            title_size = 22
            mode_size = 15
            section_size = 13
            chat_size = 17
            input_size = 17
            message_button_size = 13
            log_size = 11
            log_button_size = 12
            back_size = 15

        elif profile == "linux":
            screen_padding = 10
            screen_spacing = 7
            title_hint = 0.055
            mode_hint = 0.065
            section_title_hint = 0.032
            chat_hint = 0.370
            input_hint = 0.115
            message_buttons_hint = 0.070
            log_hint = 0.105
            log_buttons_hint = 0.060
            back_hint = 0.055

            title_size = 25
            mode_size = 16
            section_size = 14
            chat_size = 17
            input_size = 17
            message_button_size = 14
            log_size = 11
            log_button_size = 13
            back_size = 16

        else:
            screen_padding = 10
            screen_spacing = 7
            title_hint = 0.060
            mode_hint = 0.070
            section_title_hint = 0.032
            chat_hint = 0.355
            input_hint = 0.110
            message_buttons_hint = 0.072
            log_hint = 0.110
            log_buttons_hint = 0.060
            back_hint = 0.055

            title_size = 24
            mode_size = 16
            section_size = 14
            chat_size = 17
            input_size = 17
            message_button_size = 14
            log_size = 11
            log_button_size = 13
            back_size = 16

        root = BoxLayout(
            orientation="vertical",
            padding=height(screen_padding),
            spacing=height(screen_spacing),
        )

        # ---------------------------------------------------------
        # Permanent M12 system header and screen navigation
        # ---------------------------------------------------------
        self.system_header = create_system_header(
            title="AI Assistant",
            back_callback=self.go_back,
            status_provider=self.get_system_status_text,
            ai_active=True,
        )
        self.back_btn = self.system_header.back_button
        root.add_widget(self.system_header)

        # ---------------------------------------------------------
        # Hidden status state
        # ---------------------------------------------------------
        # Keep voice_status for all existing AI and voice logic, but do
        # not show the old one-line status control. Every status change
        # is written to the selectable System Log below.
        self.voice_status = TextInput(
            text="Voice ready",
            readonly=True,
            multiline=False,
            cursor_blink=False,
            size_hint=(None, None),
            size=(0, 0),
            opacity=0,
            disabled=True,
        )

        self.voice_status.bind(
            text=self.on_voice_status_changed
        )

        # ---------------------------------------------------------
        # AI / Control mode and voice-language switches
        # ---------------------------------------------------------
        mode_language_row = BoxLayout(
            orientation="horizontal",
            spacing=height(8),
            size_hint=(1, mode_hint),
        )

        self.mode_btn = Button(
            text="Mode: AI",
            font_size=font(mode_size),
            background_normal="",
        )
        self.mode_btn.bind(
            on_press=self.toggle_mode
        )
        mode_language_row.add_widget(
            self.mode_btn
        )

        self.language_btn = Button(
            text="Language: English",
            font_size=font(mode_size),
            background_normal="",
            background_color=(
                0.25,
                0.38,
                0.55,
                1,
            ),
        )
        self.language_btn.bind(
            on_press=self.cycle_voice_language
        )
        mode_language_row.add_widget(
            self.language_btn
        )

        root.add_widget(
            mode_language_row
        )

        # ---------------------------------------------------------
        # Conversation
        # ---------------------------------------------------------
        conversation_title = Label(
            text="Conversation",
            font_size=font(section_size),
            bold=True,
            size_hint=(1, section_title_hint),
            halign="left",
            valign="middle",
        )
        conversation_title.bind(
            size=lambda instance, value: setattr(
                instance,
                "text_size",
                value,
            )
        )
        root.add_widget(conversation_title)

        if platform == "android":
            # Android: use a readonly TextInput for Conversation instead of one
            # enormous markup Label. A long Label can exceed Android/Kivy
            # texture limits and render blank until the transcript is cleared.
            # TextInput renders long text incrementally and does not depend on
            # one giant texture.
            self.chat_view = TextInput(
                text=self.chat_text,
                readonly=True,
                multiline=True,
                cursor_blink=False,
                font_size=font(chat_size),
                size_hint=(1, chat_hint),
                padding=(
                    height(12),
                    height(12),
                ),
                background_color=(
                    0.025,
                    0.03,
                    0.05,
                    1,
                ),
                foreground_color=(
                    0.95,
                    0.95,
                    0.95,
                    1,
                ),
                selection_color=(
                    0.20,
                    0.45,
                    0.75,
                    0.65,
                ),
                use_bubble=True,
                use_handles=True,
                scroll_from_swipe=True,
                scroll_distance=height(12),
                scroll_timeout=150,
            )

            self.chat_view.bind(
                on_touch_down=self.on_chat_touch_down
            )

            root.add_widget(
                self.chat_view
            )

        else:
            # Desktop/Linux/macOS: ScrollView + markup Label allows
            # clickable URLs while preserving smooth scrolling.
            self.chat_scroll = ScrollView(
                size_hint=(1, chat_hint),
                do_scroll_x=False,
                do_scroll_y=True,
                bar_width=height(8),
                scroll_type=["content", "bars"],
            )

            self.chat_label = Label(
                text=self.format_chat_links(self.chat_text),
                markup=True,
                font_size=font(chat_size),
                size_hint_y=None,
                halign="left",
                valign="top",
                color=(0.95, 0.95, 0.95, 1),
                padding=(height(12), height(12)),
            )

            self.chat_label.bind(
                width=self._update_chat_label_width,
                texture_size=self._update_chat_label_height,
                on_ref_press=self.open_chat_url,
            )

            self.chat_scroll.bind(
                on_touch_down=self.on_chat_touch_down
            )

            self.chat_scroll.add_widget(self.chat_label)
            root.add_widget(self.chat_scroll)

            # Compatibility alias for existing conversation logic.
            self.chat_view = self.chat_label

        # ---------------------------------------------------------
        # Message input
        # ---------------------------------------------------------
        self.message_input = TextInput(
            hint_text="Type a message or press Voice...",
            font_size=font(input_size),
            multiline=True,
            size_hint=(1, input_hint),
            padding=(
                height(12),
                height(12),
            ),
        )

        self.message_input.bind(
            text=self.on_message_text_changed
        )

        root.add_widget(self.message_input)

        # Initialize mode colors and the input hint only after
        # message_input exists.
        self.update_mode_button()
        self.update_language_button()

        # ---------------------------------------------------------
        # Message controls
        # ---------------------------------------------------------
        message_buttons = BoxLayout(
            orientation="horizontal",
            spacing=height(6),
            size_hint=(1, message_buttons_hint),
        )

        self.voice_btn = Button(
            text="Voice",
            font_size=font(message_button_size),
            size_hint_x=0.18,
            background_normal="",
            background_color=(
                0.20,
                0.32,
                0.72,
                1,
            ),
        )
        self.voice_btn.bind(
            on_press=self.start_voice_input
        )
        message_buttons.add_widget(
            self.voice_btn
        )

        self.clear_btn = Button(
            text="Clear Messages",
            font_size=font(message_button_size),
            size_hint_x=0.32,
            background_normal="",
            background_color=(
                0.35,
                0.20,
                0.20,
                1,
            ),
        )
        self.clear_btn.bind(
            on_press=self.clear_chat
        )
        message_buttons.add_widget(
            self.clear_btn
        )

        self.copy_btn = Button(
            text="Copy Messages",
            font_size=font(message_button_size),
            size_hint_x=0.32,
            background_normal="",
            background_color=(
                0.25,
                0.28,
                0.38,
                1,
            ),
        )
        self.copy_btn.bind(
            on_press=self.copy_chat_text
        )
        message_buttons.add_widget(
            self.copy_btn
        )

        self.send_btn = Button(
            text="Send",
            font_size=font(message_button_size),
            size_hint_x=0.18,
            background_normal="",
            background_color=(
                0.10,
                0.40,
                0.30,
                1,
            ),
        )
        self.send_btn.bind(
            on_press=self.send_message
        )
        message_buttons.add_widget(
            self.send_btn
        )

        root.add_widget(message_buttons)

        # ---------------------------------------------------------
        # System Log
        # ---------------------------------------------------------
        system_log_title = Label(
            text="System Log",
            font_size=font(section_size),
            bold=True,
            size_hint=(1, section_title_hint),
            halign="left",
            valign="middle",
        )
        system_log_title.bind(
            size=lambda instance, value: setattr(
                instance,
                "text_size",
                value,
            )
        )
        root.add_widget(system_log_title)

        if platform == "android":
            self.system_log_scroll = ScrollView(
                size_hint=(1, log_hint),
                do_scroll_x=False,
                do_scroll_y=True,
                bar_width=height(8),
                scroll_type=["content", "bars"],
            )

            self.system_log_label = Label(
                text="",
                font_size=font(log_size),
                size_hint_y=None,
                halign="left",
                valign="top",
                color=(
                    0.82,
                    0.88,
                    0.92,
                    1,
                ),
                padding=(
                    height(10),
                    height(8),
                ),
            )

            self.system_log_label.bind(
                width=self._update_system_log_label_width,
                texture_size=self._update_system_log_label_height,
            )

            self.system_log_scroll.bind(
                on_touch_down=self.on_system_log_touch_down
            )

            self.system_log_scroll.add_widget(
                self.system_log_label
            )

            root.add_widget(
                self.system_log_scroll
            )

            self.system_log_view = self.system_log_label

        else:
            self.system_log_view = TextInput(
                text="",
                readonly=True,
                multiline=True,
                cursor_blink=False,
                font_size=font(log_size),
                size_hint=(1, log_hint),
                padding=(
                    height(10),
                    height(8),
                ),
                background_color=(
                    0.025,
                    0.03,
                    0.05,
                    1,
                ),
                foreground_color=(
                    0.82,
                    0.88,
                    0.92,
                    1,
                ),
                selection_color=(
                    0.20,
                    0.45,
                    0.75,
                    0.65,
                ),
                use_bubble=True,
                use_handles=True,
                scroll_from_swipe=True,
                scroll_distance=height(12),
                scroll_timeout=150,
            )

            self.system_log_view.bind(
                on_touch_down=self.on_system_log_touch_down
            )

            root.add_widget(self.system_log_view)

        # ---------------------------------------------------------
        # System Log controls
        # ---------------------------------------------------------
        system_log_buttons = BoxLayout(
            orientation="horizontal",
            spacing=height(8),
            size_hint=(1, log_buttons_hint),
        )

        self.copy_log_btn = Button(
            text="Copy Log",
            font_size=font(log_button_size),
            background_normal="",
            background_color=(
                0.22,
                0.30,
                0.44,
                1,
            ),
        )
        self.copy_log_btn.bind(
            on_press=self.copy_system_log
        )
        system_log_buttons.add_widget(
            self.copy_log_btn
        )

        self.save_log_btn = Button(
            text="Save Log",
            font_size=font(log_button_size),
            background_normal="",
            background_color=(
                0.20,
                0.38,
                0.30,
                1,
            ),
        )
        self.save_log_btn.bind(
            on_press=self.save_system_log
        )
        system_log_buttons.add_widget(
            self.save_log_btn
        )

        self.clear_log_btn = Button(
            text="Clear Log",
            font_size=font(log_button_size),
            background_normal="",
            background_color=(
                0.42,
                0.22,
                0.22,
                1,
            ),
        )
        self.clear_log_btn.bind(
            on_press=self.clear_system_log
        )
        system_log_buttons.add_widget(
            self.clear_log_btn
        )

        root.add_widget(system_log_buttons)

        # ---------------------------------------------------------
        # Back
        # ---------------------------------------------------------
        self.back_btn = Button(
            text="< Back",
            font_size=font(back_size),
            size_hint=(1, back_hint),
            background_normal="",
            background_color=(
                0.10,
                0.15,
                0.25,
                1,
            ),
        )

        self.back_btn.bind(
            on_press=self.go_back
        )

        root.add_widget(self.back_btn)
        self.add_widget(root)

        self.log_system(
            "INFO",
            "AI screen initialized",
        )
        self.log_system(
            "STATUS",
            self.voice_status.text,
        )

    # -------------------------------------------------------------
    # Persistent visible conversation
    # -------------------------------------------------------------
    @staticmethod
    def default_conversation_text():
        return (
            "M12 AI:\n"
            "Hello, Anatoliy. How can I help?"
        )

    def load_conversation_history(self):
        """
        Load the complete visible conversation from disk.

        This archive is intentionally separate from AISessionMemory.
        AISessionMemory stays bounded for OpenAI prompt context, while this
        file preserves the full transcript that the user sees on screen.
        """
        try:
            if not AI_CONVERSATION_FILE.exists():
                return self.default_conversation_text()

            saved = AI_CONVERSATION_FILE.read_text(
                encoding="utf-8"
            ).strip()

            return (
                saved
                if saved
                else self.default_conversation_text()
            )

        except Exception as error:
            print(
                "AI conversation history load error: "
                f"{type(error).__name__}: {error}"
            )
            return self.default_conversation_text()

    def schedule_conversation_save(self, delay=0.15):
        """
        Debounce transcript writes while an AI answer is streaming.
        """
        if self._conversation_save_event is not None:
            self._conversation_save_event.cancel()

        self._conversation_save_event = Clock.schedule_once(
            self.save_conversation_history,
            delay,
        )

    def save_conversation_history(self, dt=0):
        """
        Save the complete visible conversation to disk.
        """
        self._conversation_save_event = None

        try:
            AI_CONVERSATION_FILE.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temporary_file = AI_CONVERSATION_FILE.with_suffix(
                ".tmp"
            )

            temporary_file.write_text(
                self.chat_text.rstrip() + "\n",
                encoding="utf-8",
            )

            temporary_file.replace(
                AI_CONVERSATION_FILE
            )

        except Exception as error:
            print(
                "AI conversation history save error: "
                f"{type(error).__name__}: {error}"
            )

    def delete_conversation_history(self):
        """
        Remove the saved visible transcript.
        """
        if self._conversation_save_event is not None:
            self._conversation_save_event.cancel()
            self._conversation_save_event = None

        try:
            if AI_CONVERSATION_FILE.exists():
                AI_CONVERSATION_FILE.unlink()
        except Exception as error:
            print(
                "AI conversation history delete error: "
                f"{type(error).__name__}: {error}"
            )

    def render_chat_text(self):
        """
        Render the complete saved conversation into the visible widget.

        Android uses a readonly TextInput, avoiding the giant-texture failure
        of a long markup Label. Desktop keeps the markup Label so URLs remain
        clickable there.
        """
        if not hasattr(self, "chat_view"):
            return

        if getattr(self.chat_view, "markup", False):
            self.chat_view.text = self.format_chat_links(
                self.chat_text
            )
        else:
            self.chat_view.text = str(
                self.chat_text or ""
            )

    # -------------------------------------------------------------
    # Clickable URLs in Conversation
    # -------------------------------------------------------------
    @staticmethod
    def format_chat_links(text):
        """Return safe Kivy markup with clickable http/https URLs."""
        raw_text = str(text or "")
        url_pattern = re.compile(r'https?://[^\s<>"]+')

        parts = []
        last_end = 0

        for match in url_pattern.finditer(raw_text):
            start, _ = match.span()
            original_url = match.group(0)
            url = original_url
            trailing = ""

            while url and url[-1] in ".,;:!?":
                trailing = url[-1] + trailing
                url = url[:-1]

            while url.endswith(")") and url.count("(") < url.count(")"):
                trailing = ")" + trailing
                url = url[:-1]

            parts.append(escape_markup(raw_text[last_end:start]))

            if url:
                safe_url = escape_markup(url)
                parts.append(
                    "[ref=" + safe_url + "]"
                    "[color=4da3ff][u]" + safe_url +
                    "[/u][/color][/ref]"
                )

            parts.append(escape_markup(trailing))
            last_end = match.end()

        parts.append(escape_markup(raw_text[last_end:]))
        return "".join(parts)

    def copy_gallery_image(
        self,
        item,
    ):
        """
        Copy the current image on desktop.

        Linux uses xclip when available.
        macOS uses osascript/NSPasteboard-compatible file copy behavior
        by copying the downloaded image file through the Finder clipboard.

        If binary image clipboard support is unavailable, the local file
        path is copied as text instead of failing silently.
        """
        if platform == "android":
            return

        if not isinstance(
            item,
            dict,
        ):
            return

        image_url = str(
            item.get(
                "original_url",
                "",
            )
            or item.get(
                "image_url",
                "",
            )
        ).strip()

        if not image_url:
            self.voice_status.text = (
                "Copy Image failed: no image URL"
            )
            return

        title = str(
            item.get(
                "title",
                "",
            )
            or self.current_image_query
            or "m12_image"
        ).strip()

        threading.Thread(
            target=self._copy_gallery_image_worker,
            args=(
                image_url,
                title,
            ),
            daemon=True,
        ).start()

        self.voice_status.text = (
            "Copying image..."
        )

    def _copy_gallery_image_worker(
        self,
        image_url,
        title,
    ):
        try:
            request = urllib.request.Request(
                image_url,
                headers={
                    "User-Agent": (
                        "M12OS/0.5.3 image clipboard"
                    ),
                },
            )

            ssl_context = ssl.create_default_context(
                cafile=certifi.where()
            )

            with urllib.request.urlopen(
                request,
                timeout=30,
                context=ssl_context,
            ) as response:
                image_bytes = response.read()
                content_type = str(
                    response.headers.get(
                        "Content-Type",
                        "",
                    )
                ).split(
                    ";",
                    1,
                )[0].strip().lower()

            filename = self._image_filename(
                title=title,
                image_url=image_url,
                content_type=content_type,
            )

            temp_dir = (
                Path.home()
                / ".cache"
                / "m12os"
                / "clipboard"
            )
            temp_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            temp_path = (
                temp_dir
                / filename
            )
            temp_path.write_bytes(
                image_bytes
            )

            copied = False

            if sys.platform.startswith(
                "linux"
            ):
                # Try xclip with MIME type first.
                mime = (
                    content_type
                    if content_type.startswith(
                        "image/"
                    )
                    else "image/png"
                )

                try:
                    process = subprocess.run(
                        [
                            "xclip",
                            "-selection",
                            "clipboard",
                            "-t",
                            mime,
                            "-i",
                            str(temp_path),
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    copied = (
                        process.returncode == 0
                    )
                except Exception:
                    copied = False

            elif sys.platform == "darwin":
                # Copy the image file into the macOS clipboard via Finder.
                try:
                    script = (
                        'tell application "Finder" to set the clipboard '
                        f'to (POSIX file "{str(temp_path)}")'
                    )
                    process = subprocess.run(
                        [
                            "/usr/bin/osascript",
                            "-e",
                            script,
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    copied = (
                        process.returncode == 0
                    )
                except Exception:
                    copied = False

            if not copied:
                # Safe fallback: copy file path as text.
                Clipboard.copy(
                    str(temp_path)
                )

            Clock.schedule_once(
                lambda dt, ok=copied, path=str(temp_path): (
                    self._finish_image_copy(
                        ok,
                        path,
                    )
                ),
                0,
            )

        except Exception as error:
            error_message = (
                f"{type(error).__name__}: "
                f"{error}"
            )

            Clock.schedule_once(
                lambda dt, message=error_message: (
                    self._finish_image_copy_error(
                        message
                    )
                ),
                0,
            )

    def _finish_image_copy(
        self,
        copied,
        path,
    ):
        self.voice_status.text = (
            "Image copied to clipboard"
            if copied
            else (
                "Image file path copied: "
                + str(path)
            )
        )

    def _finish_image_copy_error(
        self,
        error_message,
    ):
        self.voice_status.text = (
            "Copy Image failed: "
            + str(error_message)
        )

    def share_gallery_image(
        self,
        item,
    ):
        """
        Android: download the image to a temporary cache file and open
        the native share sheet using FileProvider.
        """
        if platform != "android":
            return

        if not isinstance(
            item,
            dict,
        ):
            return

        image_url = str(
            item.get(
                "original_url",
                "",
            )
            or item.get(
                "image_url",
                "",
            )
        ).strip()

        if not image_url:
            self.voice_status.text = (
                "Share Image failed: no image URL"
            )
            return

        title = str(
            item.get(
                "title",
                "",
            )
            or self.current_image_query
            or "m12_image"
        ).strip()

        threading.Thread(
            target=self._share_gallery_image_worker,
            args=(
                image_url,
                title,
            ),
            daemon=True,
        ).start()

        self.voice_status.text = (
            "Preparing image to share..."
        )

    def _share_gallery_image_worker(
        self,
        image_url,
        title,
    ):
        try:
            print(
                "[IMAGE DEBUG] Android share worker started",
                flush=True,
            )

            request = urllib.request.Request(
                image_url,
                headers={
                    "User-Agent": (
                        "M12OS/0.5.3 image share"
                    ),
                },
            )

            ssl_context = ssl.create_default_context(
                cafile=certifi.where()
            )

            with urllib.request.urlopen(
                request,
                timeout=30,
                context=ssl_context,
            ) as response:
                image_bytes = response.read()
                content_type = str(
                    response.headers.get(
                        "Content-Type",
                        "",
                    )
                ).split(
                    ";",
                    1,
                )[0].strip().lower()

            if not image_bytes:
                raise RuntimeError(
                    "Downloaded image is empty."
                )

            filename = self._image_filename(
                title=title,
                image_url=image_url,
                content_type=content_type,
            )

            (
                _destination,
                content_uri_string,
            ) = self._save_image_android_media_store(
                image_bytes=image_bytes,
                filename=filename,
                content_type=content_type,
            )

            print(
                "[IMAGE DEBUG] MediaStore share URI: "
                + content_uri_string,
                flush=True,
            )

            from jnius import autoclass, cast

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )
            Intent = autoclass(
                "android.content.Intent"
            )
            Uri = autoclass(
                "android.net.Uri"
            )

            activity = PythonActivity.mActivity
            content_uri = Uri.parse(
                content_uri_string
            )

            share_intent = Intent(
                Intent.ACTION_SEND
            )
            share_intent.setType(
                (
                    content_type
                    if content_type.startswith("image/")
                    else "image/*"
                )
            )
            share_intent.putExtra(
                Intent.EXTRA_STREAM,
                cast(
                    "android.os.Parcelable",
                    content_uri,
                ),
            )
            share_intent.addFlags(
                Intent.FLAG_GRANT_READ_URI_PERMISSION
            )

            JavaString = autoclass(
                "java.lang.String"
            )

            chooser = Intent.createChooser(
                share_intent,
                JavaString("Share Image"),
            )
            chooser.addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK
            )

            Clock.schedule_once(
                lambda dt, intent=chooser: (
                    self._launch_android_share_intent(
                        intent
                    )
                ),
                0,
            )

        except Exception as error:
            error_message = (
                f"{type(error).__name__}: {error}"
            )

            print(
                "[IMAGE DEBUG] SHARE ERROR: "
                + error_message,
                flush=True,
            )

            Clock.schedule_once(
                lambda dt, message=error_message: (
                    self._finish_image_share_error(
                        message
                    )
                ),
                0,
            )

    @staticmethod
    def _launch_android_share_intent(
        intent,
    ):
        from jnius import autoclass

        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )

        PythonActivity.mActivity.startActivity(
            intent
        )

    def _finish_image_share_error(
        self,
        error_message,
    ):
        self.voice_status.text = (
            "Share Image failed: "
            + str(error_message)
        )

    def save_gallery_image(
        self,
        item,
    ):
        """
        Download and save one gallery image.

        Linux/macOS/desktop:
            ~/Pictures/M12 AI/

        Android:
            Saves through MediaStore into:
            Pictures/M12 AI/

        MediaStore avoids broad storage permissions on modern Android.
        """
        if not isinstance(
            item,
            dict,
        ):
            return

        image_url = str(
            item.get(
                "original_url",
                "",
            )
            or item.get(
                "image_url",
                "",
            )
        ).strip()

        if not image_url:
            self.voice_status.text = (
                "Image save failed: no image URL"
            )
            return

        title = str(
            item.get(
                "title",
                "",
            )
            or self.current_image_query
            or "m12_image"
        ).strip()

        threading.Thread(
            target=self._save_gallery_image_worker,
            args=(
                image_url,
                title,
            ),
            daemon=True,
        ).start()

        self.voice_status.text = (
            "Saving image..."
        )

    def _save_gallery_image_worker(
        self,
        image_url,
        title,
    ):
        try:
            print(
                "[IMAGE DEBUG] Android/desktop save worker started "
                f"platform={platform}",
                flush=True,
            )
            request = urllib.request.Request(
                image_url,
                headers={
                    "User-Agent": (
                        "M12OS/0.5.3 image downloader"
                    ),
                },
            )

            ssl_context = ssl.create_default_context(
                cafile=certifi.where()
            )

            with urllib.request.urlopen(
                request,
                timeout=30,
                context=ssl_context,
            ) as response:
                image_bytes = response.read()
                content_type = str(
                    response.headers.get(
                        "Content-Type",
                        "",
                    )
                ).split(
                    ";",
                    1,
                )[0].strip().lower()

            if not image_bytes:
                raise RuntimeError(
                    "Downloaded image is empty."
                )

            filename = self._image_filename(
                title=title,
                image_url=image_url,
                content_type=content_type,
            )

            if platform == "android":
                (
                    destination,
                    _content_uri,
                ) = self._save_image_android_media_store(
                    image_bytes=image_bytes,
                    filename=filename,
                    content_type=content_type,
                )
            else:
                destination = (
                    self._save_image_desktop(
                        image_bytes=image_bytes,
                        filename=filename,
                    )
                )

            Clock.schedule_once(
                lambda dt, path=destination: (
                    self._finish_image_save(
                        path
                    )
                ),
                0,
            )

        except Exception as error:
            error_message = (
                f"{type(error).__name__}: "
                f"{error}"
            )

            Clock.schedule_once(
                lambda dt, message=error_message: (
                    self._finish_image_save_error(
                        message
                    )
                ),
                0,
            )

    @staticmethod
    def _image_filename(
        title,
        image_url,
        content_type,
    ):
        """
        Build a safe file name while preserving a useful image extension.
        """
        value = str(
            title or "m12_image"
        )

        if value.lower().startswith(
            "file:"
        ):
            value = value[5:]

        value = re.sub(
            r"[^\w .()-]+",
            "_",
            value,
            flags=re.UNICODE,
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        ).strip(
            " ."
        )

        if not value:
            value = "m12_image"

        parsed_path = urllib.parse.urlparse(
            image_url
        ).path

        extension = Path(
            parsed_path
        ).suffix.lower()

        valid_extensions = {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif",
        }

        if extension not in valid_extensions:
            mime_extensions = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
                "image/gif": ".gif",
            }

            extension = mime_extensions.get(
                content_type,
                ".jpg",
            )

        if not value.lower().endswith(
            extension
        ):
            value += extension

        return value

    @staticmethod
    def _save_image_desktop(
        image_bytes,
        filename,
    ):
        pictures_dir = (
            Path.home()
            / "Pictures"
            / "M12 AI"
        )

        pictures_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination = (
            pictures_dir
            / filename
        )

        counter = 2

        while destination.exists():
            destination = (
                pictures_dir
                / (
                    f"{Path(filename).stem} "
                    f"({counter})"
                    f"{Path(filename).suffix}"
                )
            )
            counter += 1

        destination.write_bytes(
            image_bytes
        )

        return str(
            destination
        )

    @staticmethod
    def _save_image_android_media_store(
        image_bytes,
        filename,
        content_type,
    ):
        """
        Save through Android MediaStore into Pictures/M12 AI.

        Returns:
            (display_path, content_uri_string)
        """
        from jnius import autoclass

        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )
        MediaColumns = autoclass(
            "android.provider.MediaStore$MediaColumns"
        )
        ImagesMedia = autoclass(
            "android.provider.MediaStore$Images$Media"
        )
        ContentValues = autoclass(
            "android.content.ContentValues"
        )
        Environment = autoclass(
            "android.os.Environment"
        )
        BuildVersion = autoclass(
            "android.os.Build$VERSION"
        )

        activity = PythonActivity.mActivity
        resolver = activity.getContentResolver()

        values = ContentValues()
        values.put(
            MediaColumns.DISPLAY_NAME,
            filename,
        )
        values.put(
            MediaColumns.MIME_TYPE,
            (
                content_type
                if str(content_type).startswith("image/")
                else "image/jpeg"
            ),
        )

        relative_path = (
            Environment.DIRECTORY_PICTURES
            + "/M12 AI"
        )

        if int(BuildVersion.SDK_INT) >= 29:
            values.put(
                MediaColumns.RELATIVE_PATH,
                relative_path,
            )

        collection = (
            ImagesMedia.EXTERNAL_CONTENT_URI
        )

        uri = resolver.insert(
            collection,
            values,
        )

        if uri is None:
            raise RuntimeError(
                "Android MediaStore could not create image."
            )

        output_stream = resolver.openOutputStream(
            uri
        )

        if output_stream is None:
            resolver.delete(
                uri,
                None,
                None,
            )
            raise RuntimeError(
                "Android MediaStore could not open image output."
            )

        try:
            output_stream.write(
                image_bytes
            )
            output_stream.flush()
        except Exception:
            try:
                resolver.delete(
                    uri,
                    None,
                    None,
                )
            except Exception:
                pass
            raise
        finally:
            output_stream.close()

        return (
            "Pictures/M12 AI/" + filename,
            str(uri.toString()),
        )

    def _finish_image_save(
        self,
        destination,
    ):
        self.voice_status.text = (
            "Image saved: "
            + str(destination)
        )

        self.log_system(
            "INFO",
            self.voice_status.text,
        )

    def _finish_image_save_error(
        self,
        error_message,
    ):
        print(
            "[IMAGE DEBUG] SAVE ERROR: "
            + str(error_message),
            flush=True,
        )

        self.voice_status.text = (
            "Image save failed: "
            + str(error_message)
        )

        self.log_system(
            "ERROR",
            self.voice_status.text,
        )

    def open_chat_url(
        self,
        instance,
        url,
    ):
        """
        Open a clicked Conversation URL in the system browser.
        """
        target = str(url or "").strip()

        if not target.startswith(
            ("http://", "https://")
        ):
            return

        try:
            if platform == "android":
                from jnius import autoclass

                Intent = autoclass(
                    "android.content.Intent"
                )
                Uri = autoclass(
                    "android.net.Uri"
                )
                PythonActivity = autoclass(
                    "org.kivy.android.PythonActivity"
                )

                intent = Intent(
                    Intent.ACTION_VIEW,
                    Uri.parse(target),
                )

                PythonActivity.mActivity.startActivity(
                    intent
                )

                self.voice_status.text = (
                    "Opening link in browser"
                )
                return

            opened = webbrowser.open(
                target,
                new=2,
            )

            self.voice_status.text = (
                "Opening link in browser"
                if opened
                else "Unable to open browser link"
            )

        except Exception as error:
            self.voice_status.text = (
                "Unable to open browser link: "
                f"{type(error).__name__}: {error}"
            )

    # -------------------------------------------------------------
    # ImageSkill popup gallery
    # -------------------------------------------------------------
    def handle_structured_skill_result(
        self,
    ):
        """
        Display structured ImageSkill results without changing the
        Conversation/System Log layout.
        """
        result = getattr(
            self.ai_router,
            "last_skill_result",
            None,
        )

        if result is None:
            return

        action = str(
            getattr(
                result,
                "action",
                "",
            )
        )

        if action not in {
            "show_image",
            "show_image_gallery",
        }:
            return

        data = getattr(
            result,
            "data",
            None,
        )

        if not isinstance(
            data,
            dict,
        ):
            return

        images = data.get(
            "images",
            [],
        )

        if not isinstance(
            images,
            list,
        ):
            images = []

        # Backward compatibility with ImageSkill v1.
        if not images:
            image_url = str(
                data.get(
                    "image_url",
                    "",
                )
            ).strip()

            if image_url:
                images = [
                    {
                        "image_url": image_url,
                        "source_url": str(
                            data.get(
                                "source_url",
                                "",
                            )
                        ).strip(),
                        "title": str(
                            data.get(
                                "title",
                                "",
                            )
                        ).strip(),
                    }
                ]

        images = [
            item
            for item in images[:4]
            if isinstance(
                item,
                dict,
            )
            and str(
                item.get(
                    "image_url",
                    "",
                )
            ).strip()
        ]

        if not images:
            return

        self.current_image_items = images
        self.current_image_query = str(
            data.get(
                "query",
                "",
            )
        ).strip()

        self.open_image_gallery_popup()

    def open_image_gallery_popup(
        self,
        instance=None,
    ):
        """
        Open up to four ImageSkill results in a separate 2x2 popup.
        """
        if not self.current_image_items:
            return

        content = BoxLayout(
            orientation="vertical",
            spacing=height(8),
            padding=height(8),
        )

        gallery = GridLayout(
            cols=2,
            spacing=height(8),
            size_hint=(1, 1),
        )

        popup = Popup(
            title=(
                self.current_image_query
                or "Images"
            ),
            content=content,
            size_hint=(0.95, 0.92),
        )

        for index, item in enumerate(
            self.current_image_items
        ):
            image_url = str(
                item.get(
                    "image_url",
                    "",
                )
            ).strip()

            preview = AsyncImage(
                source=image_url,
                allow_stretch=True,
                keep_ratio=True,
            )

            preview._m12_image_index = index
            preview.bind(
                on_touch_down=lambda widget, touch, i=index: (
                    self.on_popup_gallery_image_touch(
                        widget,
                        touch,
                        i,
                        popup,
                    )
                )
            )

            gallery.add_widget(
                preview
            )

        close_btn = Button(
            text="Close",
            size_hint_y=None,
            height=height(48),
        )
        close_btn.bind(
            on_press=popup.dismiss
        )

        content.add_widget(
            gallery
        )
        content.add_widget(
            close_btn
        )

        popup.open()

    def on_popup_gallery_image_touch(
        self,
        instance,
        touch,
        index,
        gallery_popup,
    ):
        """
        Tap one gallery image to open it larger.
        """
        if not instance.collide_point(
            *touch.pos
        ):
            return False

        if getattr(
            touch,
            "is_mouse_scrolling",
            False,
        ):
            return False

        # Keep the gallery open underneath the large-image popup.
        # Closing the large image returns the user to the same gallery
        # so another picture can be selected.
        self.open_single_image_popup(
            index
        )
        return True

    def open_single_image_popup(
        self,
        index=0,
    ):
        """
        Open one selected gallery image at large size.
        """
        if not self.current_image_items:
            return

        index = max(
            0,
            min(
                int(index),
                len(
                    self.current_image_items
                ) - 1,
            ),
        )

        item = self.current_image_items[
            index
        ]

        image_url = str(
            item.get(
                "image_url",
                "",
            )
        ).strip()

        if not image_url:
            return

        title = str(
            item.get(
                "title",
                "",
            )
            or self.current_image_query
            or "Image"
        ).strip()

        content = BoxLayout(
            orientation="vertical",
            spacing=height(8),
            padding=height(8),
        )

        large_image = AsyncImage(
            source=image_url,
            allow_stretch=True,
            keep_ratio=True,
        )

        buttons = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=height(48),
            spacing=height(8),
        )

        share_copy_btn = Button(
            text=(
                "Share Image"
                if platform == "android"
                else "Copy Image"
            ),
        )

        save_btn = Button(
            text="Save Image",
        )

        source_btn = Button(
            text="Open Source",
        )

        close_btn = Button(
            text="Close",
        )

        buttons.add_widget(
            share_copy_btn
        )
        buttons.add_widget(
            save_btn
        )
        buttons.add_widget(
            source_btn
        )
        buttons.add_widget(
            close_btn
        )

        content.add_widget(
            large_image
        )
        content.add_widget(
            buttons
        )

        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.96, 0.94),
        )

        source_url = str(
            item.get(
                "source_url",
                "",
            )
        ).strip()

        source_btn.disabled = (
            not bool(source_url)
        )

        def save_image(
            instance=None,
        ):
            print(
                "[IMAGE DEBUG] SAVE BUTTON PRESSED",
                flush=True,
            )

            self.save_gallery_image(
                item
            )

        def open_source(
            instance=None,
        ):
            if source_url:
                self.open_chat_url(
                    None,
                    source_url,
                )

        def share_or_copy(
            instance=None,
        ):
            print(
                "[IMAGE DEBUG] SHARE/COPY BUTTON PRESSED "
                f"platform={platform}",
                flush=True,
            )

            if platform == "android":
                self.share_gallery_image(
                    item
                )
            else:
                self.copy_gallery_image(
                    item
                )

        share_copy_btn.bind(
            on_press=share_or_copy
        )
        save_btn.bind(
            on_press=save_image
        )
        source_btn.bind(
            on_press=open_source
        )
        close_btn.bind(
            on_press=popup.dismiss
        )

        popup.open()

    # -------------------------------------------------------------
    # System Log
    # -------------------------------------------------------------
    def on_voice_status_changed(
        self,
        instance,
        value,
    ):
        text = str(value or "").strip()

        if not text or text == self._last_system_status:
            return

        self._last_system_status = text
        lower = text.lower()

        if any(
            word in lower
            for word in (
                "error",
                "failed",
                "exception",
                "certificate",
                "unable",
            )
        ):
            category = "ERROR"
        elif any(
            word in lower
            for word in (
                "listening",
                "voice",
                "speaking",
                "heard",
            )
        ):
            category = "VOICE"
        elif "connect" in lower or "realtime" in lower:
            category = "OPENAI"
        else:
            category = "STATUS"

        self.log_system(
            category,
            text,
        )

    def _update_chat_label_width(
        self,
        instance,
        width,
    ):
        usable_width = max(
            1,
            width - height(24),
        )

        instance.text_size = (
            usable_width,
            None,
        )

    def _update_chat_label_height(
        self,
        instance,
        texture_size,
    ):
        instance.height = max(
            texture_size[1] + height(24),
            height(40),
        )

    def _update_system_log_label_width(
        self,
        instance,
        width,
    ):
        if platform != "android":
            return

        usable_width = max(
            1,
            width - height(20),
        )

        instance.text_size = (
            usable_width,
            None,
        )

    def _update_system_log_label_height(
        self,
        instance,
        texture_size,
    ):
        if platform != "android":
            return

        instance.height = max(
            texture_size[1] + height(16),
            height(32),
        )

    def log_system(
        self,
        category,
        message,
    ):
        text = str(message or "").strip()

        if not text:
            return

        timestamp = datetime.now().strftime(
            "%H:%M:%S"
        )
        category_text = str(category or "INFO").upper()

        line = (
            f"{timestamp}  "
            f"{category_text:<7} "
            f"{text}"
        )

        self.system_log_lines.append(line)

        if len(self.system_log_lines) > self._system_log_limit:
            self.system_log_lines = self.system_log_lines[
                -self._system_log_limit:
            ]

        if not hasattr(self, "system_log_view"):
            return

        log_text = "\n".join(
            self.system_log_lines
        )

        self.system_log_view.text = log_text

        if self._log_auto_follow:
            Clock.schedule_once(
                self.scroll_system_log_to_bottom,
                0,
            )

    def scroll_system_log_to_bottom(
        self,
        dt=0,
    ):
        if not hasattr(self, "system_log_view"):
            return

        if not self._log_auto_follow:
            return

        if (
            platform == "android"
            and hasattr(
                self,
                "system_log_scroll",
            )
        ):
            self.system_log_scroll.scroll_y = 0
            return

        try:
            end_index = len(
                self.system_log_view.text
            )
            self.system_log_view.cursor = (
                self.system_log_view.get_cursor_from_index(
                    end_index
                )
            )

            ensure_visible = getattr(
                self.system_log_view,
                "_ensure_cursor_visible",
                None,
            )

            if callable(ensure_visible):
                ensure_visible()

        except Exception as error:
            print(
                "System Log auto-scroll error: "
                f"{type(error).__name__}: {error}"
            )

    def copy_system_log(
        self,
        instance=None,
    ):
        selected = ""

        if platform != "android":
            try:
                selected = str(
                    self.system_log_view.selection_text
                ).strip()
            except Exception:
                selected = ""

        text_to_copy = selected or "\n".join(
            self.system_log_lines
        )

        if not text_to_copy:
            self.voice_status.text = (
                "System Log is empty"
            )
            return

        copied = False
        copy_errors = []

        # First use Kivy's clipboard so Android, Linux, and macOS
        # applications can paste the text normally.
        try:
            Clipboard.copy(text_to_copy)
            copied = True
        except Exception as error:
            copy_errors.append(
                "Kivy clipboard: "
                f"{type(error).__name__}: {error}"
            )

        # On macOS also use pbcopy. This works even when Kivy is using
        # the deprecated pygame clipboard provider.
        if sys.platform == "darwin":
            try:
                process = subprocess.run(
                    ["/usr/bin/pbcopy"],
                    input=text_to_copy.encode("utf-8"),
                    check=True,
                )
                copied = copied or process.returncode == 0
            except Exception as error:
                copy_errors.append(
                    "pbcopy: "
                    f"{type(error).__name__}: {error}"
                )

        if copied:
            self.voice_status.text = (
                "Selected System Log text copied"
                if selected
                else "System Log copied"
            )
        else:
            self.voice_status.text = (
                "System Log copy failed: "
                + " | ".join(copy_errors)
            )

    def save_system_log(
        self,
        instance=None,
    ):
        log_text = "\n".join(
            self.system_log_lines
        ).strip()

        if not log_text:
            self.voice_status.text = (
                "System Log is empty"
            )
            return

        try:
            logs_dir = BASE_DIR / "logs"
            logs_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            filename = (
                "system_log_"
                + datetime.now().strftime(
                    "%Y-%m-%d_%H-%M-%S"
                )
                + ".txt"
            )
            destination = logs_dir / filename
            destination.write_text(
                log_text + "\n",
                encoding="utf-8",
            )

            self.voice_status.text = (
                f"System Log saved: {filename}"
            )

        except Exception as error:
            self.voice_status.text = (
                "System Log save failed: "
                f"{type(error).__name__}: {error}"
            )

    def clear_system_log(
        self,
        instance=None,
    ):
        self.system_log_lines = []
        self._last_system_status = ""

        if hasattr(self, "system_log_view"):
            self.system_log_view.text = ""

        self.log_system(
            "INFO",
            "System Log cleared",
        )

    # -------------------------------------------------------------
    # Screen lifecycle
    # -------------------------------------------------------------
    def on_pre_enter(self, *args):
        self.update_back_button()

        # Start navigation history with the screen from which
        # the global AI button was opened.
        if (
            not self.navigation_history
            or self.navigation_history[-1] != self.return_screen
        ):
            self.navigation_history = [self.return_screen]

        Clock.schedule_once(
            self.focus_message_input,
            0.15,
        )

    def focus_message_input(self, dt):
        if (
            not self.voice_is_busy
            and not self.ai_is_busy
            and self.manager
            and self.manager.current == self.name
        ):
            self.message_input.focus = True

    def on_leave(self, *args):
        # Continuous voice intentionally keeps running while
        # Notes, Music, Calendar, and other screens are open.
        self.save_conversation_history()

    def update_back_button(self):
        screen_name = self.return_screen.replace(
            "_",
            " ",
        ).title()

        if not screen_name:
            screen_name = "Home"

        self.back_btn.text = (
            f"< Back to {screen_name}"
        )

    # -------------------------------------------------------------
    # AI / Control mode
    # -------------------------------------------------------------
    def toggle_mode(
        self,
        instance=None,
    ):
        """Switch between AI Mode and Control Mode."""
        self.set_mode(
            control_mode=not self.control_mode,
            announce=False,
        )

    def set_mode(
        self,
        control_mode,
        announce=True,
    ):
        """
        Set the active mode and synchronize both voice engines.
        """
        target_control = bool(
            control_mode
        )

        if target_control and self.realtime_voice_active:
            self.stop_realtime_voice()

        self.control_mode = target_control
        self.continuous_voice = False

        if self.voice_service is not None:
            self.voice_service.stop_speaking()

        self.voice_btn.text = "Voice"
        self.update_mode_button()

        if not announce:
            return None

        if self.control_mode:
            return "Control Mode activated."

        return "AI Mode activated."

    @staticmethod
    def get_mode_command(
        message,
    ):
        """
        Return "ai", "control", or None for a reserved command.

        The check is intentionally broad because speech recognition may
        return phrases such as "open AI assistant" instead of "AI mode".
        """
        import re
        import unicodedata

        text = str(
            message
        ).strip().lower().replace(
            "’",
            "'",
        )

        text = unicodedata.normalize(
            "NFKD",
            text,
        )

        text = "".join(
            character
            for character in text
            if not unicodedata.combining(
                character
            )
        )

        text = re.sub(
            r"[^a-z0-9а-яё\s']+",
            " ",
            text,
        )

        text = " ".join(
            text.split()
        )

        ai_commands = {
            "ai mode",
            "mode ai",
            "switch to ai mode",
            "switch into ai mode",
            "change to ai mode",
            "go to ai mode",
            "talk to ai",
            "conversation mode",
            "assistant mode",
            "ai assistant",
            "open ai assistant",
            "switch to ai assistant",
            "go to ai assistant",
            "m12 ai",
            "open m12 ai",
        }

        control_commands = {
            "control mode",
            "mode control",
            "switch to control mode",
            "switch into control mode",
            "change to control mode",
            "go to control mode",
            "command mode",
            "application mode",
            "application control",
            "control applications",
            "app control mode",
        }

        if text in ai_commands:
            return "ai"

        if text in control_commands:
            return "control"

        # Accept harmless extra words added by speech recognition.
        if (
            "ai mode" in text
            or "ai assistant" in text
            or "m12 ai" in text
            or "conversation mode" in text
        ):
            return "ai"

        if (
            "control mode" in text
            or "command mode" in text
            or "application mode" in text
            or "application control" in text
        ):
            return "control"

        return None

    @staticmethod
    def load_voice_language():
        """
        Load the voice-recognition language saved by the AI screen.
        """
        if not AI_SETTINGS_FILE.exists():
            return "en"

        try:
            with AI_SETTINGS_FILE.open(
                "r",
                encoding="utf-8",
            ) as file:
                settings = json.load(file)

            if not isinstance(
                settings,
                dict,
            ):
                return "en"

            return VoiceService.normalize_language(
                settings.get(
                    "voice_language",
                    "en",
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            print(
                "AI screen language load error: "
                f"{type(error).__name__}: {error}"
            )
            return "en"

    def cycle_voice_language(
        self,
        instance=None,
    ):
        """
        Cycle English -> Russian -> Auto.
        """
        codes = [
            code
            for code, _ in VOICE_LANGUAGES
        ]

        try:
            current_index = codes.index(
                self.voice_language
            )
        except ValueError:
            current_index = 0

        next_index = (
            current_index + 1
        ) % len(codes)

        self.set_voice_language(
            codes[next_index]
        )

    def set_voice_language(
        self,
        language,
    ):
        """
        Apply and persist the selected recognition language.
        """
        normalized = (
            VoiceService.normalize_language(
                language
            )
        )

        self.voice_language = normalized

        if self.voice_service is None:
            VoiceService.save_voice_language(
                normalized
            )
        else:
            self.voice_service.set_transcription_language(
                normalized,
                save=True,
            )

        if self.realtime_voice_service is not None:
            self.realtime_voice_service.set_language(
                normalized
            )

        self.update_language_button()

        language_name = dict(
            VOICE_LANGUAGES
        ).get(
            normalized,
            "Auto",
        )

        self.voice_status.text = (
            f"Voice language: {language_name}"
        )

    def update_language_button(
        self,
    ):
        language_name = dict(
            VOICE_LANGUAGES
        ).get(
            self.voice_language,
            "Auto",
        )

        self.language_btn.text = (
            f"Language: {language_name}"
        )

        colors = {
            "en": (
                0.18,
                0.42,
                0.65,
                1,
            ),
            "ru": (
                0.48,
                0.28,
                0.62,
                1,
            ),
            "auto": (
                0.32,
                0.42,
                0.42,
                1,
            ),
        }

        self.language_btn.background_color = (
            colors.get(
                self.voice_language,
                colors["auto"],
            )
        )

    def update_mode_button(
        self,
    ):
        """
        Update the one visible mode switch.
        """
        if self.control_mode:
            self.mode_btn.text = "Mode: Control"
            self.mode_btn.background_color = (
                0.72,
                0.34,
                0.16,
                1,
            )
            self.voice_status.text = "Control Mode"
            self.message_input.hint_text = (
                "Enter an M12 command..."
            )
        else:
            self.mode_btn.text = "Mode: AI"
            self.mode_btn.background_color = (
                0.20,
                0.48,
                0.76,
                1,
            )
            self.voice_status.text = "AI Mode"
            self.message_input.hint_text = (
                "Ask M12 AI anything..."
            )

    def get_system_status_text(self):
        if (
            self.manager
            and self.manager.has_screen("home")
        ):
            home = self.manager.get_screen("home")
            provider = getattr(
                home,
                "get_system_status_text",
                None,
            )

            if callable(provider):
                return provider()

        return "WiFi"


    def refresh_status_bar(self):
        if hasattr(self, "system_header"):
            self.system_header.refresh(0)

    def on_enter(
        self,
        *args,
    ):
        self.refresh_status_bar()
        """
        Opening the AI Assistant always activates AI Mode.

        This ensures an application command such as "Open AI Assistant"
        changes both the visible screen and the operating mode.
        """
        self.control_mode = False
        self.update_mode_button()

        self.render_chat_text()
        Clock.schedule_once(
            lambda dt: self.render_chat_text(),
            0,
        )
        Clock.schedule_once(
            self.scroll_to_bottom,
            0.05,
        )

        if self.realtime_voice_active:
            self.voice_btn.text = "Stop Voice"
            self.voice_status.text = (
                "Realtime connected — listening"
            )
        elif not self.continuous_voice:
            self.voice_btn.text = "Voice"
            self.voice_status.text = "AI Mode"

    # -------------------------------------------------------------
    # Voice recognition
    # -------------------------------------------------------------
    def start_voice_input(
        self,
        instance=None,
    ):
        """
        AI Mode uses Realtime speech-to-speech.
        Control Mode uses the existing command recorder.
        """
        if self.control_mode:
            self.start_control_voice_input(
                instance
            )
            return

        if self.realtime_voice_active:
            self.stop_realtime_voice()
            return

        self.start_realtime_voice()

    def start_realtime_voice(
        self,
    ):
        if self.realtime_voice_active:
            return

        self.voice_btn.text = "Connecting..."
        self.voice_status.text = (
            "Connecting Realtime voice..."
        )
        self.set_controls_enabled(False)
        self.mode_btn.disabled = False
        self.language_btn.disabled = False
        self.voice_btn.disabled = False

        threading.Thread(
            target=self._start_realtime_worker,
            daemon=True,
        ).start()

    def _start_realtime_worker(
        self,
    ):
        try:
            if self.realtime_voice_service is None:
                self.realtime_voice_service = (
                    RealtimeVoiceService(
                        on_status=(
                            self.on_realtime_status
                        ),
                        on_user_transcript=(
                            self.on_realtime_user_transcript
                        ),
                        on_text_delta=(
                            self.on_realtime_text_delta
                        ),
                        on_text_done=(
                            self.on_realtime_text_done
                        ),
                        on_speech_started=(
                            self.on_realtime_speech_started
                        ),
                        on_speech_stopped=(
                            self.on_realtime_speech_stopped
                        ),
                        on_local_request=(
                            self.on_realtime_local_request
                        ),
                        on_local_answer=(
                            self.on_realtime_local_answer
                        ),
                        on_error=(
                            self.on_realtime_error
                        ),
                    )
                )

            self.realtime_voice_service.language = (
                self.voice_language
            )

            self.realtime_voice_service.start_conversation(
                timeout=20.0
            )

            Clock.schedule_once(
                self._finish_realtime_started,
                0,
            )

        except Exception as error:
            # Python clears the exception variable after leaving an
            # except block. Save the message before scheduling the
            # Kivy callback so the delayed lambda cannot raise NameError.
            error_message = (
                f"{type(error).__name__}: "
                f"{error}"
            )

            Clock.schedule_once(
                lambda dt, message=error_message: (
                    self._finish_realtime_error(
                        message
                    )
                ),
                0,
            )

    def _finish_realtime_started(
        self,
        dt=0,
    ):
        self.realtime_voice_active = True
        self.continuous_voice = False
        self.voice_btn.text = "Stop Voice"
        self.voice_status.text = (
            "Realtime connected — listening"
        )
        self.set_controls_enabled(True)
        self.voice_btn.text = "Stop Voice"

    def stop_realtime_voice(
        self,
    ):
        service = self.realtime_voice_service

        self.realtime_voice_active = False
        self.realtime_answer_active = False
        self.realtime_answer_text = ""

        if service is not None:
            try:
                service.stop_conversation()
            except Exception as error:
                print(
                    "Realtime stop error: "
                    f"{type(error).__name__}: {error}"
                )

        self.voice_btn.text = "Voice"
        self.voice_status.text = "Realtime voice stopped"
        self.set_controls_enabled(True)

    def _finish_realtime_error(
        self,
        error_message,
    ):
        message = str(error_message)

        # A local skill may finish before OpenAI starts a response.
        # In that case cancelling the nonexistent response is normal and
        # must not be shown as a Realtime failure.
        if "response_cancel_not_active" in message:
            self.realtime_answer_active = False
            self.realtime_answer_text = ""

            if self.realtime_voice_active:
                self.voice_btn.text = "Stop Voice"
                self.voice_status.text = (
                    "Realtime connected — listening"
                )
            else:
                self.voice_btn.text = "Voice"
                self.voice_status.text = "Voice ready"

            self.set_controls_enabled(True)
            return

        self.realtime_voice_active = False
        self.voice_btn.text = "Voice"
        self.voice_status.text = (
            f"Realtime error: {message}"
        )
        self.set_controls_enabled(True)

    def on_realtime_status(
        self,
        message,
    ):
        Clock.schedule_once(
            lambda dt: self._apply_realtime_status(
                message
            ),
            0,
        )

    def _apply_realtime_status(
        self,
        message,
    ):
        if self.realtime_voice_active:
            self.voice_status.text = str(
                message
            )

    def on_realtime_user_transcript(
        self,
        transcript,
    ):
        Clock.schedule_once(
            lambda dt: self._apply_realtime_user_transcript(
                transcript
            ),
            0,
        )

    def _apply_realtime_user_transcript(
        self,
        transcript,
    ):
        text = str(
            transcript
        ).strip()

        if not text:
            return

        # While a local skill answer is being spoken, the always-on
        # Realtime microphone may hear M12's own speaker output. Ignore
        # those echo transcripts, but still allow a real Stop/Стоп command.
        if self.realtime_local_speech_active:
            if self.is_local_speech_stop_command(text):
                self.stop_realtime_local_speech()
            return

        mode_command = self.get_mode_command(
            text
        )

        if mode_command == "control":
            service = self.realtime_voice_service

            if service is not None:
                service.cancel_response()

            self.append_message(
                speaker="You",
                message=text,
            )

            self.stop_realtime_voice()

            answer = self.set_mode(
                control_mode=True,
                announce=True,
            )

            self.append_message(
                speaker="M12 AI",
                message=answer,
            )

            self.voice_status.text = answer

            # Continue hands-free in Control Mode.
            self.continuous_voice = True
            Clock.schedule_once(
                self.begin_voice_cycle,
                0.7,
            )
            return

        self.append_message(
            speaker="You",
            message=text,
        )

        self.session_memory.add_user(
            text,
            route="normal",
        )

        try:
            self.ai_router.capture_automatic_fact(
                text
            )
        except Exception as error:
            print(
                "Permanent-memory capture error: "
                f"{type(error).__name__}: {error}"
            )

    @staticmethod
    def is_local_speech_stop_command(
        message,
    ):
        """Return True for a command that interrupts local-skill speech."""
        text = str(message).strip().lower().replace("’", "'")
        text = re.sub(r"[^a-z0-9а-яё'\s]+", " ", text)
        text = " ".join(text.split())

        stop_commands = {
            "stop",
            "stop please",
            "please stop",
            "pause",
            "quiet",
            "be quiet",
            "stop talking",
            "stop speaking",
            "стоп",
            "остановись",
            "останови",
            "хватит",
            "замолчи",
            "перестань",
            "перестань говорить",
        }

        return text in stop_commands

    def stop_realtime_local_speech(
        self,
        dt=0,
    ):
        """Immediately stop a local-skill spoken answer and keep listening."""
        self.realtime_local_speech_active = False

        if self.voice_service is not None:
            try:
                self.voice_service.stop_speaking()
            except Exception as error:
                print(
                    "Local-speech stop error: "
                    f"{type(error).__name__}: {error}"
                )

        service = self.realtime_voice_service

        if service is not None:
            try:
                service.resume_microphone_after_local_answer()
            except Exception as error:
                print(
                    "Realtime microphone resume error: "
                    f"{type(error).__name__}: {error}"
                )

        if self.realtime_voice_active:
            self.voice_status.text = (
                "Realtime connected — listening"
            )

    def on_realtime_local_request(
        self,
        transcript,
    ):
        """Run local skills on Kivy's main thread and return their result."""
        text = str(transcript).strip()

        if not text:
            return False, ""

        if self.realtime_local_speech_active:
            if self.is_local_speech_stop_command(text):
                Clock.schedule_once(
                    self.stop_realtime_local_speech,
                    0,
                )

            # Swallow everything heard while local TTS is active. Most of
            # it is the device hearing its own speaker. Returning handled
            # prevents OpenAI Realtime from creating a second response.
            return True, ""

        completed = threading.Event()
        result_holder = {
            "handled": False,
            "answer": "",
        }

        def run_local_router(dt):
            try:
                handled, answer = (
                    self.ai_router.process_local(
                        message=text,
                        ai_screen=self,
                    )
                )

                result_holder["handled"] = bool(
                    handled
                )
                result_holder["answer"] = str(
                    answer or ""
                ).strip()

                if result_holder["handled"]:
                    self.handle_structured_skill_result()

            except Exception as error:
                print(
                    "Realtime local routing error: "
                    f"{type(error).__name__}: {error}"
                )

            finally:
                completed.set()

        Clock.schedule_once(
            run_local_router,
            0,
        )

        if not completed.wait(timeout=5.0):
            print(
                "Realtime local routing timed out."
            )
            return False, ""

        return (
            result_holder["handled"],
            result_holder["answer"],
        )

    def on_realtime_local_answer(
        self,
        answer,
    ):
        Clock.schedule_once(
            lambda dt: self._apply_realtime_local_answer(
                answer
            ),
            0,
        )

    def _apply_realtime_local_answer(
        self,
        answer,
    ):
        text = str(answer or "").strip()

        if not text:
            return

        # Cancel any Realtime assistant response that may have started for
        # this turn. A handled local skill must be the only speaking path.
        service = self.realtime_voice_service

        if service is not None:
            try:
                service.cancel_response()
            except Exception as error:
                print(
                    "Realtime cancel before local answer error: "
                    f"{type(error).__name__}: {error}"
                )

        # Keep the Realtime microphone active while a local answer is
        # spoken so Stop/Стоп can interrupt it. Echo transcripts are
        # suppressed by the guards above.
        self.realtime_local_speech_active = True

        self.append_message(
            speaker="M12 AI",
            message=text,
        )

        self.session_memory.add_assistant(
            text,
            route="local",
        )

        self.voice_status.text = (
            "Answering with local skill..."
        )

        threading.Thread(
            target=self._speak_realtime_local_answer,
            args=(text,),
            daemon=True,
        ).start()

    def _speak_realtime_local_answer(
        self,
        answer,
    ):
        error_message = ""

        try:
            if self.voice_service is None:
                self.voice_service = VoiceService()
                self.voice_service.set_transcription_language(
                    self.voice_language,
                    save=False,
                )

            self.voice_service.speak_text(
                answer
            )

        except Exception as error:
            error_message = (
                f"{type(error).__name__}: {error}"
            )
            print(
                "Realtime local-answer speech error: "
                f"{error_message}"
            )

        Clock.schedule_once(
            lambda dt: self._finish_realtime_local_answer(
                error_message
            ),
            0,
        )

    def _finish_realtime_local_answer(
        self,
        error_message="",
    ):
        self.realtime_local_speech_active = False
        service = self.realtime_voice_service

        if service is not None:
            try:
                service.resume_microphone_after_local_answer()
            except Exception as error:
                print(
                    "Realtime microphone resume error: "
                    f"{type(error).__name__}: {error}"
                )

        if error_message:
            self.voice_status.text = (
                "Local answer speech failed"
            )
        elif self.realtime_voice_active:
            self.voice_status.text = (
                "Realtime connected — listening"
            )

    def on_realtime_text_delta(
        self,
        delta,
    ):
        Clock.schedule_once(
            lambda dt: self._apply_realtime_text_delta(
                delta
            ),
            0,
        )

    def _apply_realtime_text_delta(
        self,
        delta,
    ):
        if not self.realtime_answer_active:
            self.realtime_answer_active = True
            self.realtime_answer_text = ""
            self.append_message(
                speaker="M12 AI",
                message="",
            )

        self.realtime_answer_text += str(
            delta
        )

        self.replace_last_ai_message(
            self.realtime_answer_text
        )

    def on_realtime_text_done(
        self,
        text,
    ):
        Clock.schedule_once(
            lambda dt: self._apply_realtime_text_done(
                text
            ),
            0,
        )

    def _apply_realtime_text_done(
        self,
        text,
    ):
        answer = str(
            text
        ).strip()

        if answer:
            if not self.realtime_answer_active:
                self.append_message(
                    speaker="M12 AI",
                    message=answer,
                )
            elif answer != self.realtime_answer_text.strip():
                self.realtime_answer_text = answer
                self.replace_last_ai_message(
                    answer
                )

            self.session_memory.add_assistant(
                answer,
                route="normal",
            )

        self.realtime_answer_active = False
        self.realtime_answer_text = ""

        if self.realtime_voice_active:
            self.voice_status.text = (
                "Realtime connected — listening"
            )

    def on_realtime_speech_started(
        self,
    ):
        Clock.schedule_once(
            lambda dt: setattr(
                self.voice_status,
                "text",
                "Listening...",
            ),
            0,
        )

    def on_realtime_speech_stopped(
        self,
    ):
        Clock.schedule_once(
            lambda dt: setattr(
                self.voice_status,
                "text",
                "Thinking...",
            ),
            0,
        )

    def on_realtime_error(
        self,
        message,
    ):
        Clock.schedule_once(
            lambda dt: self._finish_realtime_error(
                str(message)
            ),
            0,
        )

    def start_control_voice_input(
        self,
        instance=None,
    ):
        # Press Stop Voice while M12 is speaking to interrupt it.
        if self.speech_is_busy:
            if self.voice_service is not None:
                self.voice_service.stop_speaking()

            self.speech_is_busy = False
            self.continuous_voice = False
            self.voice_btn.text = "Voice"
            self.voice_status.text = "Voice answer stopped"
            self.set_controls_enabled(True)
            return

        # Press Voice once to start continuous conversation.
        # Press Stop Voice to stop automatic listening.
        if self.continuous_voice:
            self.continuous_voice = False
            self.voice_btn.text = "Voice"
            self.voice_status.text = "Voice conversation stopped"
            return

        if self.voice_is_busy or self.ai_is_busy:
            return

        self.continuous_voice = True
        self.begin_voice_cycle()

    def begin_voice_cycle(self, dt=0):
        if not self.continuous_voice:
            return

        if (
            self.voice_is_busy
            or self.ai_is_busy
            or self.speech_is_busy
        ):
            return

        self.voice_is_busy = True
        self.set_controls_enabled(False)

        self.voice_btn.text = "Listening..."
        self.voice_status.text = (
            "Speak now — recording for 6 seconds"
        )

        self.message_input.focus = False

        threading.Thread(
            target=self.record_voice_worker,
            daemon=True,
        ).start()

    def record_voice_worker(self):
        try:
            if self.voice_service is None:
                self.voice_service = VoiceService()
                self.voice_service.set_transcription_language(
                    self.voice_language,
                    save=False,
                )

            recognized_text = (
                self.voice_service
                .record_and_transcribe(
                    duration=6
                )
            )

            Clock.schedule_once(
                lambda dt: self.voice_success(
                    recognized_text
                ),
                0,
            )

        except Exception as error:
            error_message = (
                f"{type(error).__name__}: {error}"
            )

            Clock.schedule_once(
                lambda dt: self.voice_error(
                    error_message
                ),
                0,
            )

    def voice_success(
        self,
        recognized_text,
    ):
        recognized_text = str(
            recognized_text
        ).strip()

        self.voice_is_busy = False
        self.voice_btn.text = "Voice"

        if not recognized_text:
            self.voice_status.text = (
                "No speech was recognized"
            )
            self.set_controls_enabled(True)
            return

        self.voice_status.text = (
            f'Heard: "{recognized_text}"'
        )

        # Show recognized speech without switching out of
        # continuous voice mode.
        self.setting_voice_text = True
        self.message_input.text = recognized_text
        self.setting_voice_text = False

        # Automatically submit the voice command.
        Clock.schedule_once(
            lambda dt: self.send_voice_message(
                recognized_text
            ),
            0.20,
        )

    def handle_global_mode_command(
        self,
        message,
        source="typed",
    ):
        """
        Handle mode commands before AI, plugins, or busy checks.
        """
        mode_command = self.get_mode_command(
            message
        )

        if mode_command is None:
            return False

        self.append_message(
            speaker="You",
            message=str(message).strip(),
        )

        if mode_command == "control":
            if self.realtime_voice_active:
                self.stop_realtime_voice()

            answer = self.set_mode(
                control_mode=True,
                announce=True,
            )

            self.append_message(
                speaker="M12 AI",
                message=answer,
            )

            if source == "voice":
                self.continuous_voice = True
                Clock.schedule_once(
                    self.begin_voice_cycle,
                    0.7,
                )

        else:
            self.continuous_voice = False

            answer = self.set_mode(
                control_mode=False,
                announce=True,
            )

            self.append_message(
                speaker="M12 AI",
                message=answer,
            )

            if source == "voice":
                Clock.schedule_once(
                    lambda dt: self.start_realtime_voice(),
                    0.7,
                )

        self.voice_status.text = answer
        return True

    def send_voice_message(
        self,
        recognized_text,
    ):
        # Global mode commands must work even while AI is busy.
        if self.handle_global_mode_command(
            recognized_text,
            source="voice",
        ):
            self.message_input.text = ""
            return

        if self.ai_is_busy:
            return

        self.message_input.text = ""

        self.process_message(
            user_message=recognized_text,
            source="voice",
        )

    def voice_error(
        self,
        error_message,
    ):
        self.voice_is_busy = False
        self.set_controls_enabled(True)

        error_text = str(error_message)
        error_lower = error_text.lower()

        # Silence is normal in continuous conversation mode.
        # Do not stop Voice; tell the user and listen again.
        silence_error = (
            "recording was silent" in error_lower
            or "no speech was recognized" in error_lower
            or "speak louder" in error_lower
        )

        if silence_error and self.continuous_voice:
            self.voice_btn.text = "Stop Voice"
            self.voice_status.text = (
                "I didn't hear you. Please speak again."
            )

            # Do not add silence notices to the chat history.
            # This lets the user keep reading a scrolled-up answer
            # without the conversation jumping back to the bottom.
            Clock.schedule_once(
                self.begin_voice_cycle,
                1.2,
            )
            return

        # A real microphone, network, or transcription error
        # stops continuous mode.
        self.continuous_voice = False
        self.voice_btn.text = "Voice"
        self.voice_status.text = (
            "Voice recognition failed"
        )

        self.append_message(
            speaker="M12 AI",
            message=(
                "Voice error:\n"
                f"{error_text}"
            ),
        )

    # -------------------------------------------------------------
    # Chat sizing
    # -------------------------------------------------------------
    def update_chat_text_size(
        self,
        instance,
        width,
    ):
        return None

    def update_chat_height(
        self,
        instance,
        texture_size,
    ):
        return None

    # -------------------------------------------------------------
    # Typing mode
    # -------------------------------------------------------------
    def on_message_text_changed(
        self,
        instance,
        value,
    ):
        """
        Stop continuous listening when the user begins typing.

        Text inserted by voice recognition is ignored so voice
        conversation mode can continue normally.
        """
        if self.setting_voice_text:
            return

        typed_text = str(value).strip()

        if (
            typed_text
            and self.continuous_voice
            and not self.voice_is_busy
        ):
            self.continuous_voice = False
            self.voice_btn.text = "Voice"
            self.voice_status.text = "Typing mode"

            # A previously scheduled voice cycle may still run,
            # but begin_voice_cycle() will now exit immediately
            # because continuous_voice is False.

    # -------------------------------------------------------------
    # Typed message
    # -------------------------------------------------------------
    def send_message(
        self,
        instance=None,
    ):
        user_message = (
            self.message_input.text.strip()
        )

        if not user_message:
            return

        # Global mode commands must bypass all busy checks.
        if self.handle_global_mode_command(
            user_message,
            source="typed",
        ):
            self.message_input.text = ""
            return

        if self.voice_is_busy or self.ai_is_busy:
            return

        self.message_input.text = ""

        self.process_message(
            user_message=user_message,
            source="typed",
        )

    # -------------------------------------------------------------
    # Shared processing for typed and voice messages
    # -------------------------------------------------------------
    def process_message(
        self,
        user_message,
        source="typed",
    ):
        user_message = str(
            user_message
        ).strip()

        if not user_message:
            self.set_controls_enabled(True)
            return

        self.ai_is_busy = True
        self.set_controls_enabled(False)

        if source == "voice":
            if self.control_mode:
                self.voice_status.text = (
                    "Processing M12 command..."
                )
            else:
                self.voice_status.text = (
                    "Processing AI question..."
                )

        self.append_message(
            speaker="You",
            message=user_message,
        )

        # Reserved mode commands always work in either mode and
        # never go to a plugin or OpenAI.
        mode_command = self.get_mode_command(
            user_message
        )

        if mode_command == "ai":
            answer = self.set_mode(
                control_mode=False,
                announce=True,
            )
            self.finish_local_command(
                answer
            )
            return

        if mode_command == "control":
            answer = self.set_mode(
                control_mode=True,
                announce=True,
            )
            self.finish_local_command(
                answer
            )
            return

        # CONTROL MODE:
        # Only local M12 application commands are accepted.
        if self.control_mode:
            try:
                handled, local_answer = AIActions.execute(
                    message=user_message,
                    ai_screen=self,
                )
            except Exception as error:
                handled = True
                local_answer = (
                    "Local command error: "
                    f"{type(error).__name__}: {error}"
                )

            if handled:
                self.finish_local_command(
                    local_answer
                )
                return

            try:
                plugin_handled, plugin_answer = (
                    self.ai_router.process_local(
                        message=user_message,
                        ai_screen=self,
                    )
                )
            except Exception as error:
                plugin_handled = True
                plugin_answer = (
                    "Plugin command error: "
                    f"{type(error).__name__}: {error}"
                )

            if plugin_handled:
                self.finish_local_command(
                    plugin_answer
                )
                return

            self.finish_unrecognized_control_command(
                user_message
            )
            return

        # AI MODE:
        # Typed requests check M12 local skills first. This lets Weather,
        # Notes, Calendar, and other local capabilities answer with live
        # device/app data before falling back to OpenAI.
        if source == "typed":
            try:
                local_handled, local_answer = (
                    self.ai_router.process_local(
                        message=user_message,
                        ai_screen=self,
                    )
                )
            except Exception as error:
                local_handled = False
                local_answer = ""
                print(
                    "Typed local routing error: "
                    f"{type(error).__name__}: {error}"
                )

            if local_handled:
                self.append_message(
                    speaker="M12 AI",
                    message=str(local_answer or "").strip(),
                )

                self.handle_structured_skill_result()

                self.ai_is_busy = False
                self.set_controls_enabled(True)
                self.voice_btn.text = "Voice"
                self.voice_status.text = "AI Mode"
                return

        # Not handled locally: send the request to OpenAI.
        self.show_ai_screen_for_question()

        # Create an empty answer immediately. Text will appear
        # incrementally as OpenAI streams it.
        self.append_message(
            speaker="M12 AI",
            message="",
        )

        self.streaming_answer = ""
        self.streaming_spoken_length = 0

        # Typed AI requests are text-only.
        # Voice requests keep the spoken-answer queue.
        if source == "voice":
            self.start_streaming_speech_queue()
        else:
            self.speech_queue = None
            self.speech_is_busy = False

        threading.Thread(
            target=self.request_ai_response,
            args=(user_message,),
            daemon=True,
        ).start()


    def is_clear_ai_request(self, message):
        """Return True only for an intentional voice request to AI."""
        import re
        import unicodedata

        text = str(message).strip().lower().replace("’", "'")
        text = unicodedata.normalize("NFKD", text)
        text = "".join(
            character for character in text
            if not unicodedata.combining(character)
        )
        text = re.sub(r"[^a-z0-9а-яё\s']+", " ", text)
        text = " ".join(text.split())

        if not text:
            return False

        # Local plugin commands must be allowed through to AIRouter.
        # Notes filtering examples:
        #   "show work notes"
        #   "filter notes by personal"
        #   "open shopping notes"
        note_command_words = (
            "note",
            "notes",
        )

        if any(
            word in text.split()
            for word in note_command_words
        ):
            return True

        # Explicitly addressing the assistant always means AI.
        ai_prefixes = (
            "ai ", "m12 ", "m 12 ", "assistant ",
            "hey ai ", "hello ai ", "ask ai ",
        )
        if text in {"ai", "m12", "m 12", "assistant"}:
            return True
        if text.startswith(ai_prefixes):
            return True

        # Normal information questions.
        question_starts = (
            "what ", "who ", "when ", "where ", "why ", "how ",
            "which ", "whose ", "is ", "are ", "am ", "do ",
            "does ", "did ", "can ", "could ", "would ", "should ",
            "will ", "tell me ", "explain ", "describe ",
            "weather ", "forecast ", "temperature ",
            "что ", "кто ", "когда ", "где ", "почему ", "как ",
            "какая ", "какой ", "какие ", "сколько ",
            "расскажи ", "объясни ", "покажи мне ",
        )
        return text.startswith(question_starts)

    def show_voice_notice(self, text, seconds=1.6):
        """Show a short visible message even when the AI screen is hidden."""
        label = Label(
            text=str(text),
            font_size=font(22),
            halign="center",
            valign="middle",
        )
        label.bind(
            size=lambda instance, value: setattr(
                instance,
                "text_size",
                value,
            )
        )

        popup = Popup(
            title="M12 Voice",
            content=label,
            size_hint=(0.82, 0.24),
            auto_dismiss=True,
        )
        popup.open()
        Clock.schedule_once(
            lambda dt: popup.dismiss(),
            seconds,
        )

    def finish_unrecognized_control_command(
        self,
        message,
    ):
        """Reject an unknown Control Mode command without calling AI."""
        self.show_voice_notice(
            f'Command not recognized: "{message}"'
        )

        self.append_message(
            speaker="M12 Control",
            message=(
                "Command not recognized. "
                "Say 'AI mode' to return to AI conversation."
            ),
        )

        self.ai_is_busy = False
        self.set_controls_enabled(True)

        if self.continuous_voice:
            self.voice_btn.text = "Stop Voice"
            self.voice_status.text = "Listening again..."
            Clock.schedule_once(
                self.begin_voice_cycle,
                1.4,
            )
        else:
            self.voice_btn.text = "Voice"
            self.voice_status.text = "Control Mode"

    def finish_unrecognized_voice_command(self, message):
        self.show_voice_notice(
            f'Command not recognized: "{message}"'
        )

        self.append_message(
            speaker="M12 AI",
            message=(
                "Command not recognized. Say an app command such as "
                "'Open Notes', or begin a question with 'AI'."
            ),
        )

        self.ai_is_busy = False
        self.set_controls_enabled(True)

        if self.continuous_voice:
            self.voice_btn.text = "Stop Voice"
            self.voice_status.text = "Listening again..."
            Clock.schedule_once(self.begin_voice_cycle, 1.8)
        else:
            self.voice_btn.text = "Voice"
            self.voice_status.text = "Voice ready"

    def show_ai_screen_for_question(self):
        manager = self.manager
        if manager is None or manager.current == self.name:
            return

        current = manager.current
        if current and manager.has_screen(current):
            self.return_screen = current
            self.navigation_history = [current]

        manager.current = self.name

    def finish_local_command(self, answer):
        self.show_voice_notice(answer)

        self.append_message(
            speaker="M12 AI",
            message=answer,
        )

        self.ai_is_busy = False
        self.set_controls_enabled(True)

        if self.continuous_voice:
            self.voice_btn.text = "Stop Voice"
            self.voice_status.text = "Listening again..."

            Clock.schedule_once(
                self.begin_voice_cycle,
                1.8,
            )
        else:
            self.voice_btn.text = "Voice"
            self.voice_status.text = "Voice ready"

    def request_ai_response(
        self,
        user_message,
    ):
        try:
            answer = self.ai_router.process_ai_stream(
                message=user_message,
                on_delta=self.receive_ai_delta,
            )

        except Exception as error:
            answer = (
                "AI router error: "
                f"{type(error).__name__}: {error}"
            )

        Clock.schedule_once(
            lambda dt: self.finish_streaming_response(
                answer
            ),
            0,
        )

    def receive_ai_delta(
        self,
        delta,
    ):
        """
        Called from the worker thread for each text fragment.
        """
        Clock.schedule_once(
            lambda dt: self.apply_ai_delta(
                delta
            ),
            0,
        )

    def apply_ai_delta(
        self,
        delta,
    ):
        self.streaming_answer += str(
            delta
        )

        self.replace_last_ai_message(
            self.streaming_answer
        )

        self.enqueue_completed_sentences()

    def replace_last_ai_message(
        self,
        answer,
    ):
        marker = "\n\nM12 AI:\n"
        position = self.chat_text.rfind(
            marker
        )

        if position < 0:
            self.append_message(
                speaker="M12 AI",
                message=answer,
            )
            return

        self.chat_text = (
            self.chat_text[:position]
            + marker
            + str(answer)
        )

        self.schedule_chat_refresh()
        self.schedule_conversation_save()

    def schedule_chat_refresh(
        self,
        delay=0.06,
    ):
        """
        Refresh the visible conversation at most about 16 times per second.

        Replacing TextInput.text for every tiny streaming token causes visible
        flashing and selection loss, especially with the pygame window backend.
        """
        self._chat_refresh_pending = True

        if self._chat_refresh_event is not None:
            return

        self._chat_refresh_event = Clock.schedule_once(
            self.flush_chat_refresh,
            delay,
        )

    def flush_chat_refresh(
        self,
        dt=0,
    ):
        self._chat_refresh_event = None

        if not self._chat_refresh_pending:
            return

        self._chat_refresh_pending = False

        scroll_widget = getattr(
            self,
            "chat_scroll",
            None,
        )

        old_scroll_y = (
            getattr(
                scroll_widget,
                "scroll_y",
                0,
            )
            if scroll_widget is not None
            else 0
        )

        self.render_chat_text()

        if self._chat_auto_follow:
            Clock.schedule_once(
                self.scroll_to_bottom,
                0,
            )
            Clock.schedule_once(
                self.scroll_to_bottom,
                0.04,
            )
            return

        if scroll_widget is not None:
            def restore_scroll(dt):
                scroll_widget.scroll_y = old_scroll_y

            Clock.schedule_once(
                restore_scroll,
                0,
            )

    def finish_streaming_response(
        self,
        answer,
    ):
        final_answer = str(
            answer
        ).strip()

        if (
            final_answer
            and final_answer != self.streaming_answer.strip()
        ):
            self.streaming_answer = final_answer
            self.replace_last_ai_message(
                final_answer
            )

        self._chat_refresh_pending = True
        self.flush_chat_refresh()

        self.enqueue_completed_sentences(
            flush=True
        )

        if self.speech_queue is not None:
            self.speech_queue.put(
                None
            )

        self.ai_is_busy = False
        self.set_controls_enabled(True)

        if not self.streaming_answer.strip():
            self.finish_speaking_answer(
                "Empty AI response"
            )

    def start_streaming_speech_queue(
        self,
    ):
        self.speech_queue = queue.Queue()
        self.speech_is_busy = True
        self.voice_status.text = "Answering..."
        self.voice_btn.text = "Stop Voice"

        threading.Thread(
            target=self.streaming_speech_worker,
            daemon=True,
        ).start()

    def enqueue_completed_sentences(
        self,
        flush=False,
    ):
        text = self.streaming_answer

        if flush:
            boundary = len(text)
        else:
            matches = list(
                re.finditer(
                    r"[.!?](?:\s|$)",
                    text,
                )
            )

            if not matches:
                return

            boundary = matches[-1].end()

        if boundary <= self.streaming_spoken_length:
            return

        chunk = text[
            self.streaming_spoken_length:boundary
        ].strip()

        self.streaming_spoken_length = boundary

        if chunk and self.speech_queue is not None:
            self.speech_queue.put(
                chunk
            )

    def streaming_speech_worker(
        self,
    ):
        error_message = ""

        try:
            if self.voice_service is None:
                self.voice_service = VoiceService()
                self.voice_service.set_transcription_language(
                    self.voice_language,
                    save=False,
                )

            while True:
                item = self.speech_queue.get()

                if item is None:
                    break

                self.voice_service.speak_text(
                    item
                )

        except Exception as error:
            error_message = (
                f"{type(error).__name__}: {error}"
            )
            print(
                "Voice answer error: "
                f"{error_message}"
            )

        Clock.schedule_once(
            lambda dt: self.finish_speaking_answer(
                error_message
            ),
            0,
        )

    def finish_speaking_answer(
        self,
        error_message="",
    ):
        self.speech_is_busy = False
        self.set_controls_enabled(True)

        if error_message:
            self.voice_status.text = (
                "Voice answer failed"
            )
        else:
            self.voice_status.text = (
                "Voice ready"
            )

        if self.continuous_voice:
            self.voice_btn.text = "Stop Voice"
            self.voice_status.text = (
                "Listening again..."
            )

            Clock.schedule_once(
                self.begin_voice_cycle,
                0.55,
            )
        else:
            self.voice_btn.text = "Voice"

            if (
                self.manager
                and self.manager.current == self.name
            ):
                self.message_input.focus = True

    # -------------------------------------------------------------
    # Controls
    # -------------------------------------------------------------
    def set_controls_enabled(
        self,
        enabled,
    ):
        disabled = not enabled

        self.voice_btn.disabled = disabled
        self.send_btn.disabled = disabled
        self.clear_btn.disabled = disabled
        self.copy_btn.disabled = disabled
        self.back_btn.disabled = disabled
        self.mode_btn.disabled = False
        self.language_btn.disabled = False

    # -------------------------------------------------------------
    # Append message
    # -------------------------------------------------------------
    def on_chat_touch_down(
        self,
        instance,
        touch,
    ):
        target = (
            self.chat_scroll
            if hasattr(
                self,
                "chat_scroll",
            )
            else self.chat_view
        )

        if not target.collide_point(
            *touch.pos
        ):
            return False

        self._chat_auto_follow = False
        return False

    def on_system_log_touch_down(
        self,
        instance,
        touch,
    ):
        target = (
            self.system_log_scroll
            if (
                platform == "android"
                and hasattr(
                    self,
                    "system_log_scroll",
                )
            )
            else self.system_log_view
        )

        if not target.collide_point(
            *touch.pos
        ):
            return False

        self._log_auto_follow = False
        return False

    def append_message(
        self,
        speaker,
        message,
    ):
        speaker_text = str(speaker)
        message_text = str(message)

        self._chat_auto_follow = True
        self._log_auto_follow = True

        if speaker_text == "You":
            self.log_system(
                "USER",
                message_text,
            )
        elif message_text.strip():
            self.log_system(
                "AI",
                message_text,
            )

        self.chat_text += (
            f"\n\n{str(speaker)}:\n"
            f"{str(message)}"
        )

        self._chat_refresh_pending = True
        self.flush_chat_refresh()
        self.schedule_conversation_save()

        Clock.schedule_once(
            self.scroll_to_bottom,
            0,
        )
        Clock.schedule_once(
            self.scroll_to_bottom,
            0.05,
        )

    def copy_chat_text(
        self,
        instance=None,
    ):
        """
        Copy selected text, or the full conversation when nothing is selected.

        macOS uses pbcopy directly because Kivy's pygame clipboard provider
        can crash the application.
        """
        selected = ""

        if platform != "android":
            try:
                selected = str(
                    self.chat_view.selection_text
                ).strip()
            except Exception:
                selected = ""

        text_to_copy = (
            selected
            if selected
            else self.chat_text
        )

        try:
            if sys.platform == "darwin":
                subprocess.run(
                    ["pbcopy"],
                    input=text_to_copy,
                    text=True,
                    check=True,
                )
            else:
                Clipboard.copy(
                    text_to_copy
                )

            self.voice_status.text = (
                "Selected text copied"
                if selected
                else "Conversation copied"
            )

        except Exception as error:
            self.voice_status.text = (
                "Copy failed: "
                f"{type(error).__name__}: {error}"
            )

    def restore_chat_scroll(
        self,
        scroll_y,
    ):
        return None

    def scroll_to_bottom(
        self,
        dt=0,
    ):
        """
        Keep the newest conversation text visible automatically.
        """
        if not self._chat_auto_follow:
            return

        if hasattr(
            self,
            "chat_scroll",
        ):
            self.chat_scroll.scroll_y = 0
            return

        try:
            end_index = len(
                self.chat_view.text
            )

            cursor = (
                self.chat_view.get_cursor_from_index(
                    end_index
                )
            )

            self.chat_view.cursor = cursor

            ensure_visible = getattr(
                self.chat_view,
                "_ensure_cursor_visible",
                None,
            )

            if callable(ensure_visible):
                ensure_visible()

        except Exception as error:
            print(
                "AI chat auto-scroll error: "
                f"{type(error).__name__}: {error}"
            )

    # -------------------------------------------------------------
    # Clear conversation
    # -------------------------------------------------------------
    def clear_chat(
        self,
        instance=None,
    ):
        if self.voice_is_busy or self.ai_is_busy:
            return

        self.continuous_voice = False
        self.voice_btn.text = "Voice"

        self.ai_router.clear_memory()
        self.delete_conversation_history()

        self.chat_text = (
            "M12 AI:\n"
            "Conversation and session memory cleared. "
            "How can I help?"
        )

        if self._chat_refresh_event is not None:
            self._chat_refresh_event.cancel()
            self._chat_refresh_event = None

        self._chat_refresh_pending = False
        self._chat_auto_follow = True
        self._log_auto_follow = True
        self.render_chat_text()
        self.message_input.text = ""
        self.voice_status.text = (
            "Control Mode"
            if self.control_mode
            else "AI Mode"
        )

        self.set_controls_enabled(True)
        self.save_conversation_history()

        Clock.schedule_once(
            self.scroll_to_bottom,
            0.05,
        )

    # -------------------------------------------------------------
    # Navigation
    # -------------------------------------------------------------
    def go_back(
        self,
        instance=None,
    ):
        if self.voice_is_busy or self.ai_is_busy:
            return

        self.continuous_voice = False
        self.voice_btn.text = "Voice"

        target = self.return_screen

        if (
            not target
            or target == "ai"
            or not self.manager.has_screen(target)
        ):
            target = "home"

        self.manager.current = target