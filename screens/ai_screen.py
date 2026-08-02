import queue
import re
import threading

from kivy.clock import Clock
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
from services.voice_service import VoiceService
from utils.ui_scale import font, height


class AIScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.return_screen = "home"

        # Keep one router alive so AI conversation memory remains.
        self.ai_router = AIRouter()

        # Voice service is created only when it is first needed.
        self.voice_service = None
        self.voice_is_busy = False
        self.ai_is_busy = False
        self.continuous_voice = False
        self.setting_voice_text = False
        self.speech_is_busy = False

        # Streaming answer and speech-queue state.
        self.streaming_answer = ""
        self.streaming_spoken_length = 0
        self.speech_queue = None

        # AI Mode is the default. In AI Mode every message goes to AI.
        # Control Mode is used only for M12 application commands.
        self.control_mode = False
        self.navigation_history = []

        self.chat_text = (
            "[b]M12 AI:[/b]\n"
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
            font_size=font(42),
            bold=True,
            size_hint=(1, 0.11),
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
        self.voice_status = Label(
            text="Voice ready",
            font_size=font(18),
            size_hint=(1, 0.05),
            color=(0.70, 0.85, 1, 1),
            halign="center",
            valign="middle",
        )

        self.voice_status.bind(
            size=lambda instance, value: setattr(
                instance,
                "text_size",
                value,
            )
        )

        root.add_widget(self.voice_status)

        # ---------------------------------------------------------
        # Conversation area
        # ---------------------------------------------------------
        self.chat_scroll = ScrollView(
            size_hint=(1, 0.49),
            do_scroll_x=False,
            bar_width=height(8),
        )

        self.chat_label = Label(
            text=self.chat_text,
            markup=True,
            font_size=font(26),
            size_hint_y=None,
            halign="left",
            valign="top",
            padding=(
                height(12),
                height(12),
            ),
        )

        self.chat_label.bind(
            width=self.update_chat_text_size,
            texture_size=self.update_chat_height,
        )

        self.chat_scroll.add_widget(self.chat_label)
        root.add_widget(self.chat_scroll)

        # ---------------------------------------------------------
        # AI / Control mode switch
        # ---------------------------------------------------------
        self.mode_btn = Button(
            text="Mode: AI",
            font_size=font(22),
            size_hint=(1, 0.07),
            background_normal="",
        )
        self.mode_btn.bind(
            on_press=self.toggle_mode
        )
        root.add_widget(self.mode_btn)

        # ---------------------------------------------------------
        # Message input
        # ---------------------------------------------------------
        self.message_input = TextInput(
            hint_text="Type a message or press Voice...",
            font_size=font(26),
            multiline=True,
            size_hint=(1, 0.13),
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

        # ---------------------------------------------------------
        # Voice, Clear, and Send
        # ---------------------------------------------------------
        action_row = BoxLayout(
            orientation="horizontal",
            spacing=height(8),
            size_hint=(1, 0.09),
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

        action_row.add_widget(self.voice_btn)

        self.clear_btn = Button(
            text="Clear",
            font_size=font(23),
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

        action_row.add_widget(self.clear_btn)

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

        action_row.add_widget(self.send_btn)
        root.add_widget(action_row)

        # ---------------------------------------------------------
        # Back
        # ---------------------------------------------------------
        self.back_btn = Button(
            text="< Back",
            font_size=font(27),
            size_hint=(1, 0.06),
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
        """Set the active mode and keep the button synchronized."""
        self.control_mode = bool(
            control_mode
        )
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

        if not self.continuous_voice:
            self.voice_btn.text = "Voice"
            self.voice_status.text = "AI Mode"

    # -------------------------------------------------------------
    # Voice recognition
    # -------------------------------------------------------------
    def start_voice_input(
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
        Handle AI/Control mode commands before any busy checks.

        Returns True when a mode command was recognized.
        """
        mode_command = self.get_mode_command(
            message
        )

        if mode_command is None:
            return False

        # Preserve continuous voice across mode switches.
        # If voice conversation was active before the switch,
        # automatically resume listening afterward.
        resume_voice = bool(
            self.continuous_voice
            or source == "voice"
        )

        if self.voice_service is not None:
            self.voice_service.stop_speaking()

        self.speech_is_busy = False
        self.voice_is_busy = False
        self.ai_is_busy = False
        self.set_controls_enabled(True)

        self.append_message(
            speaker="You",
            message=str(message).strip(),
        )

        answer = self.set_mode(
            control_mode=(
                mode_command == "control"
            ),
            announce=True,
        )

        self.append_message(
            speaker="M12 AI",
            message=answer,
        )

        if resume_voice:
            self.continuous_voice = True
            self.voice_btn.text = "Stop Voice"
            self.voice_status.text = answer

            Clock.schedule_once(
                self.begin_voice_cycle,
                0.8,
            )
        else:
            self.continuous_voice = False
            self.voice_btn.text = "Voice"
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
        instance.text_size = (
            max(
                width - height(24),
                1,
            ),
            None,
        )

    def update_chat_height(
        self,
        instance,
        texture_size,
    ):
        instance.height = max(
            texture_size[1] + height(24),
            self.chat_scroll.height,
        )

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
        marker = "\n\n[b]M12 AI:[/b]\n"
        position = self.chat_text.rfind(
            marker
        )

        if position < 0:
            self.append_message(
                speaker="M12 AI",
                message=answer,
            )
            return

        safe_answer = escape_markup(
            str(answer)
        )

        self.chat_text = (
            self.chat_text[:position]
            + marker
            + safe_answer
        )

        self.chat_label.text = self.chat_text

        Clock.schedule_once(
            self.scroll_to_bottom,
            0.02,
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
        self.back_btn.disabled = disabled
        self.mode_btn.disabled = False

    # -------------------------------------------------------------
    # Append message
    # -------------------------------------------------------------
    def append_message(
        self,
        speaker,
        message,
    ):
        # ScrollView uses 0 for the bottom and 1 for the top.
        # Auto-scroll only when the user was already reading near
        # the bottom. If they scrolled up, preserve that position.
        was_near_bottom = self.chat_scroll.scroll_y <= 0.08
        previous_scroll_y = self.chat_scroll.scroll_y

        safe_speaker = escape_markup(
            str(speaker)
        )

        safe_message = escape_markup(
            str(message)
        )

        self.chat_text += (
            f"\n\n[b]{safe_speaker}:[/b]\n"
            f"{safe_message}"
        )

        self.chat_label.text = self.chat_text

        if was_near_bottom:
            Clock.schedule_once(
                self.scroll_to_bottom,
                0.05,
            )
        else:
            Clock.schedule_once(
                lambda dt: self.restore_chat_scroll(
                    previous_scroll_y
                ),
                0.05,
            )

    def restore_chat_scroll(
        self,
        scroll_y,
    ):
        self.chat_scroll.scroll_y = max(
            0.0,
            min(1.0, float(scroll_y)),
        )

    def scroll_to_bottom(
        self,
        dt,
    ):
        self.chat_scroll.scroll_y = 0

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
            "[b]M12 AI:[/b]\n"
            "Conversation and memory cleared. "
            "How can I help?"
        )

        self.chat_label.text = self.chat_text
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