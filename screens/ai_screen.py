import json
import queue
import re
import threading
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.utils import escape_markup

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from services.ai_actions import AIActions
from services.ai_router import AIRouter
from services.ai_session_memory import get_ai_session_memory
from services.realtime_voice_service import RealtimeVoiceService
from services.voice_service import VoiceService
from utils.ui_scale import font, height

BASE_DIR = Path(__file__).resolve().parent.parent
AI_SETTINGS_FILE = BASE_DIR / "config" / "ai_settings.json"

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

        self.chat_text = (
            "M12 AI:\n"
            "Hello, Anatoliy. How can I help?"
        )

        root = BoxLayout(
            orientation="vertical",
            padding=height(16),
            spacing=height(10),
        )

        # ---------------------------------------------------------
        # Title
        # ---------------------------------------------------------
        title = Label(
            text="AI Assistant",
            font_size=font(36),
            bold=True,
            size_hint=(1, 0.07),
            halign="center",
            valign="middle",
        )

        title.bind(
            size=lambda instance, value: setattr(
                instance,
                "text_size",
                value,
            )
        )

        root.add_widget(title)

        # ---------------------------------------------------------
        # Voice status
        # ---------------------------------------------------------
        self.voice_status = TextInput(
            text="Voice ready",
            readonly=True,
            multiline=False,
            cursor_blink=False,
            font_size=font(17),
            size_hint=(1, 0.05),
            padding=(
                height(10),
                height(8),
            ),
            background_color=(
                0.08,
                0.10,
                0.16,
                1,
            ),
            foreground_color=(
                0.72,
                0.88,
                1.00,
                1,
            ),
            selection_color=(
                0.20,
                0.45,
                0.75,
                0.65,
            ),
        )

        self.voice_status.bind(
            text=self.on_voice_status_changed
        )

        root.add_widget(self.voice_status)

        # ---------------------------------------------------------
        # AI / Control mode and voice-language switches
        # ---------------------------------------------------------
        mode_language_row = BoxLayout(
            orientation="horizontal",
            spacing=height(8),
            size_hint=(1, 0.06),
        )

        self.mode_btn = Button(
            text="Mode: AI",
            font_size=font(22),
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
            font_size=font(22),
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
            font_size=font(20),
            bold=True,
            size_hint=(1, 0.035),
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

        self.chat_view = TextInput(
            text=self.chat_text,
            readonly=True,
            multiline=True,
            font_size=font(26),
            size_hint=(1, 0.30),
            padding=(
                height(12),
                height(12),
            ),
            background_color=(
                0.06,
                0.07,
                0.10,
                1,
            ),
            foreground_color=(
                0.95,
                0.95,
                0.95,
                1,
            ),
            cursor_color=(
                0.80,
                0.88,
                1.00,
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

        # ---------------------------------------------------------
        # Message input
        # ---------------------------------------------------------
        self.message_input = TextInput(
            hint_text="Type a message or press Voice...",
            font_size=font(26),
            multiline=True,
            size_hint=(1, 0.10),
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
            spacing=height(8),
            size_hint=(1, 0.075),
        )

        self.voice_btn = Button(
            text="Voice",
            font_size=font(23),
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
            font_size=font(20),
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
            font_size=font(20),
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
            font_size=font(23),
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
            font_size=font(20),
            bold=True,
            size_hint=(1, 0.035),
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

        self.system_log_view = TextInput(
            text="",
            readonly=True,
            multiline=True,
            cursor_blink=False,
            font_size=font(15),
            size_hint=(1, 0.16),
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
        )
        root.add_widget(self.system_log_view)

        # ---------------------------------------------------------
        # System Log controls
        # ---------------------------------------------------------
        system_log_buttons = BoxLayout(
            orientation="horizontal",
            spacing=height(8),
            size_hint=(1, 0.055),
        )

        self.copy_log_btn = Button(
            text="Copy Log",
            font_size=font(18),
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
            font_size=font(18),
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
            font_size=font(18),
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
            font_size=font(27),
            size_hint=(1, 0.05),
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

        self.system_log_view.text = "\n".join(
            self.system_log_lines
        )

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

        try:
            if sys.platform == "darwin":
                subprocess.run(
                    ["pbcopy"],
                    input=text_to_copy,
                    text=True,
                    check=True,
                )
            else:
                Clipboard.copy(text_to_copy)

            self.voice_status.text = (
                "Selected System Log text copied"
                if selected
                else "System Log copied"
            )

        except Exception as error:
            self.voice_status.text = (
                "System Log copy failed: "
                f"{type(error).__name__}: {error}"
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
        pass

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

    def on_enter(
        self,
        *args,
    ):
        """
        Opening the AI Assistant always activates AI Mode.

        This ensures an application command such as "Open AI Assistant"
        changes both the visible screen and the operating mode.
        """
        self.control_mode = False
        self.update_mode_button()

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
        self.realtime_voice_active = False
        self.voice_btn.text = "Voice"
        self.voice_status.text = (
            f"Realtime error: {error_message}"
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
        # Every typed or spoken message goes to AI. This allows short
        # natural follow-ups such as "more details" or "why?".
        self.show_ai_screen_for_question()

        # Create an empty answer immediately. Text will appear
        # incrementally as OpenAI streams it.
        self.append_message(
            speaker="M12 AI",
            message="",
        )

        self.streaming_answer = ""
        self.streaming_spoken_length = 0
        self.start_streaming_speech_queue()

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

        self._chat_auto_follow = True
        self.schedule_chat_refresh()

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

        old_scroll_y = getattr(
            self.chat_view,
            "scroll_y",
            0,
        )

        try:
            selection_from = (
                self.chat_view.selection_from
            )
            selection_to = (
                self.chat_view.selection_to
            )
        except Exception:
            selection_from = None
            selection_to = None

        self.chat_view.text = self.chat_text

        if self._chat_auto_follow:
            # TextInput calculates line geometry on the next Clock cycle.
            # Scroll after that calculation, and repeat once for long answers.
            Clock.schedule_once(
                self.scroll_to_bottom,
                0,
            )
            Clock.schedule_once(
                self.scroll_to_bottom,
                0.04,
            )
            return

        try:
            self.chat_view.scroll_y = old_scroll_y

            if (
                selection_from is not None
                and selection_to is not None
                and selection_from != selection_to
            ):
                self.chat_view.select_text(
                    selection_from,
                    selection_to,
                )
        except Exception:
            pass

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
        """
        Let the user scroll up without the view immediately snapping back.

        New messages re-enable automatic scrolling to the bottom.
        """
        if not self.chat_view.collide_point(
            *touch.pos
        ):
            return False

        if (
            getattr(
                touch,
                "button",
                "",
            )
            in {
                "scrollup",
                "scrolldown",
            }
            or getattr(
                touch,
                "is_mouse_scrolling",
                False,
            )
        ):
            self._chat_auto_follow = False

        return False

    def append_message(
        self,
        speaker,
        message,
    ):
        speaker_text = str(speaker)
        message_text = str(message)

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

        self._chat_auto_follow = True

        self.chat_text += (
            f"\n\n{str(speaker)}:\n"
            f"{str(message)}"
        )

        self._chat_refresh_pending = True
        self.flush_chat_refresh()

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

        TextInput.cursor expects a (column, row) pair, not a character index.
        """
        if not self._chat_auto_follow:
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

            # Force Kivy to bring the cursor line into the viewport.
            ensure_visible = getattr(
                self.chat_view,
                "_ensure_cursor_visible",
                None,
            )

            if callable(ensure_visible):
                ensure_visible()

            # Fallback for providers where cursor visibility alone is delayed.
            self.chat_view.scroll_y = max(
                0,
                getattr(
                    self.chat_view,
                    "scroll_y",
                    0,
                ),
            )

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

        self.chat_text = (
            "M12 AI:\n"
            "Conversation and session memory cleared. "
            "How can I help?"
        )

        if self._chat_refresh_event is not None:
            self._chat_refresh_event.cancel()
            self._chat_refresh_event = None

        self._chat_refresh_pending = False
        self.chat_view.text = self.chat_text
        self.message_input.text = ""
        self.voice_status.text = (
            "Control Mode"
            if self.control_mode
            else "AI Mode"
        )

        self.set_controls_enabled(True)

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