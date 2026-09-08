# M12 OS Brainstorm Screen
#
# One human + two AIs (ChatGPT and Claude) collaborate on a problem the
# user poses. The two AIs take turns responding to each other, seeing
# the full transcript so far. Either AI can pause the loop to ask the
# user a clarifying question; the loop resumes once the user answers.
import json
import threading
from datetime import datetime
from pathlib import Path

from kivy.core.clipboard import Clipboard
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

import subprocess
import sys

from services.chatgpt_client import ChatGPTClient, ChatGPTClientError
from services.claude_client import ClaudeClient, ClaudeClientError
from utils.system_header import create_system_header
from utils.ui_scale import (
    button_font,
    button_height,
    text_font,
    small_font,
    input_font,
    row_height,
    small_row_height,
    padding_size,
    spacing_size,
)

BASE_DIR = Path(__file__).resolve().parent.parent
BRAINSTORM_DIR = BASE_DIR / "data" / "brainstorm"
SESSION_FILE = BRAINSTORM_DIR / "session.json"
LEGACY_SESSION_FILE = BRAINSTORM_DIR / "session.txt"
ARCHIVE_DIR = BRAINSTORM_DIR / "archive"

MAX_TURNS = 24

FINAL_DECISION_PROMPT = (
    "Please stop debating now and state your single final decision on "
    "this topic. Prefix your reply with 'SOLUTION:' followed by the "
    "concrete decision and a short justification."
)

CHATGPT_SYSTEM_PROMPT = (
    "You are ChatGPT, collaborating with another AI named Claude to "
    "solve a problem posed by a human user. Read the full conversation "
    "so far, including the human's messages and Claude's replies. "
    "Build on the discussion: propose ideas, critique Claude's "
    "suggestions constructively, and work together toward a concrete, "
    "practical solution. Keep replies focused and reasonably short.\n\n"
    "Do not debate indefinitely. Once you and Claude have covered the "
    "key options and trade-offs (usually within a few exchanges), work "
    "toward a specific final decision rather than continuing to "
    "brainstorm more alternatives.\n\n"
    "If you genuinely need more information from the human user before "
    "continuing, reply with ONLY a line starting with "
    "'QUESTION_FOR_USER:' followed by your question, and nothing else.\n\n"
    "A final decision requires BOTH of you -- reaching it is a two-step "
    "handshake, not a unilateral call:\n"
    "1. When you believe you have a good answer, reply with a line "
    "starting with 'SOLUTION:' followed by your proposed decision and "
    "a short justification. This is only a PROPOSAL, not final yet.\n"
    "2. If Claude's most recent message proposed a solution (started "
    "with 'SOLUTION:') and you genuinely agree with it as the final "
    "answer, reply with a line starting with 'AGREED:' followed by the "
    "final decision (incorporating any small refinement you want to "
    "add). Only use 'AGREED:' when you truly accept it as final -- if "
    "you disagree or want changes, continue the discussion normally "
    "instead, or propose your own 'SOLUTION:' if it differs. If you "
    "independently reach essentially the same conclusion Claude just "
    "proposed, restating it with your own 'SOLUTION:' also counts as "
    "convergence."
)

CLAUDE_SYSTEM_PROMPT = (
    "You are Claude, collaborating with another AI named ChatGPT to "
    "solve a problem posed by a human user. Read the full conversation "
    "so far, including the human's messages and ChatGPT's replies. "
    "Build on the discussion: propose ideas, critique ChatGPT's "
    "suggestions constructively, and work together toward a concrete, "
    "practical solution. Keep replies focused and reasonably short.\n\n"
    "Do not debate indefinitely. Once you and ChatGPT have covered the "
    "key options and trade-offs (usually within a few exchanges), work "
    "toward a specific final decision rather than continuing to "
    "brainstorm more alternatives.\n\n"
    "If you genuinely need more information from the human user before "
    "continuing, reply with ONLY a line starting with "
    "'QUESTION_FOR_USER:' followed by your question, and nothing else.\n\n"
    "A final decision requires BOTH of you -- reaching it is a two-step "
    "handshake, not a unilateral call:\n"
    "1. When you believe you have a good answer, reply with a line "
    "starting with 'SOLUTION:' followed by your proposed decision and "
    "a short justification. This is only a PROPOSAL, not final yet.\n"
    "2. If ChatGPT's most recent message proposed a solution (started "
    "with 'SOLUTION:') and you genuinely agree with it as the final "
    "answer, reply with a line starting with 'AGREED:' followed by the "
    "final decision (incorporating any small refinement you want to "
    "add). Only use 'AGREED:' when you truly accept it as final -- if "
    "you disagree or want changes, continue the discussion normally "
    "instead, or propose your own 'SOLUTION:' if it differs. If you "
    "independently reach essentially the same conclusion ChatGPT just "
    "proposed, restating it with your own 'SOLUTION:' also counts as "
    "convergence."
)


class BrainstormScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.return_screen = "home"

        # Transcript entries: list of (speaker, text) tuples.
        # speaker is one of: "You", "ChatGPT", "Claude"
        self.transcript = []

        self.chatgpt_client = ChatGPTClient()
        self.claude_client = ClaudeClient()

        self.running = False
        self.debate_thread = None
        self.stop_requested = False
        self.waiting_for_user = False
        self.pause_event = threading.Event()

        # Persists across errors/stops within the same app session so
        # "Start Brainstorm" can resume an interrupted discussion instead
        # of silently discarding it. Reset to 0 only when a brand-new
        # topic is started (see start_brainstorm / new_topic).
        self.turn_index = 0

        # The turn_index value at which the CURRENT run should stop.
        # Reset to (turn_index + MAX_TURNS) every time a run is launched
        # (Start/Continue/Get Final Decision), so hitting the cap once
        # never permanently freezes later attempts -- each explicit user
        # action grants a fresh batch of turns.
        self.turn_budget_end = MAX_TURNS

        # Set by "Get Final Decision Now" while a turn is already in
        # flight; picked up at the top of the next loop iteration so the
        # forcing note doesn't get lost mid-request.
        self.pending_final_decision = False

        # A solution proposed by one AI, awaiting the other AI's
        # explicit agreement before it's treated as final. Reset
        # whenever a brand-new topic starts.
        self.pending_solution = None

        # The finalized decision text once both AIs converge (set by
        # _announce_solution). None means no decision reached yet.
        self.final_decision = None

        # A user-supplied title overriding the auto-derived one (first
        # "You" message). None means "use the auto-derived title".
        self.custom_title = None

        # Snapshot of self.transcript as of the last successful archive,
        # used to skip creating a redundant duplicate archive when
        # nothing has actually changed since then.
        self._last_archived_transcript = None

        self._save_event = None

        self.load_session()
        self.build_ui()

    # -------------------------------------------------------------
    # UI
    # -------------------------------------------------------------
    @staticmethod
    def _bind_disabled_dim(widget, enabled_color, disabled_color=(0.18, 0.18, 0.20, 1)):
        """
        Make a widget's background actually gray out when disabled.

        Kivy's default disabled styling only swaps the built-in text
        color and background image automatically -- it does NOT dim a
        custom background_color when background_normal="" is used (as
        every button on this screen does), so disabled buttons would
        otherwise look identical to enabled ones. This binds the visual
        state directly to the `disabled` property so it always matches,
        no matter which code path toggles it.
        """
        widget.background_color = disabled_color if widget.disabled else enabled_color
        widget.bind(
            disabled=lambda inst, val, ec=enabled_color, dc=disabled_color: setattr(
                inst, "background_color", dc if val else ec
            )
        )

    def build_ui(self):
        root = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size(),
        )

        self.system_header = create_system_header(
            title="Brainstorm",
            back_callback=self.go_back,
            status_provider=self.get_system_status_text,
            ai_active=False,
        )
        root.add_widget(self.system_header)

        # ---------------------------------------------------------
        # Current topic title (always visible, regardless of scroll
        # position -- the topic text itself lives inside the scrollable
        # transcript and gets scrolled out of view immediately since the
        # screen auto-scrolls to the latest message).
        # ---------------------------------------------------------
        self.topic_title_panel = BoxLayout(
            size_hint=(1, 0.055),
            padding=(spacing_size(), spacing_size() // 2 or 1),
        )

        with self.topic_title_panel.canvas.before:
            Color(0.08, 0.12, 0.20, 1)
            self._topic_title_bg_rect = Rectangle(
                pos=self.topic_title_panel.pos, size=self.topic_title_panel.size
            )

        self.topic_title_panel.bind(
            pos=lambda inst, val: setattr(self._topic_title_bg_rect, "pos", val),
            size=lambda inst, val: setattr(self._topic_title_bg_rect, "size", val),
        )

        self.topic_title_label = Label(
            text="No active topic",
            font_size=text_font(),
            bold=True,
            color=(0.70, 0.85, 1, 1),
            halign="center",
            valign="middle",
            shorten=True,
            shorten_from="right",
        )
        self.topic_title_label.bind(
            size=lambda inst, val: setattr(inst, "text_size", val)
        )
        self.topic_title_panel.add_widget(self.topic_title_label)
        root.add_widget(self.topic_title_panel)

        # ---------------------------------------------------------
        # Transcript
        # ---------------------------------------------------------
        # A read-only TextInput (not a Label) so the user can click-drag
        # to select text and press Ctrl+C, same as the System Log on the
        # AI screen. Labels cannot be selected or copied in Kivy.
        #
        # Wrapped in a ScrollView for a visible right-side scrollbar --
        # TextInput has no scrollbar of its own. scroll_type=['bars']
        # means only dragging the bar itself scrolls; dragging inside
        # the text keeps working for selection, so Copy Transcript is
        # unaffected.
        self.chat_scroll = ScrollView(
            size_hint=(1, 0.445),
            do_scroll_x=False,
            do_scroll_y=True,
            bar_width=spacing_size(),
            scroll_type=["bars"],
            bar_color=(0.45, 0.55, 0.70, 0.9),
            bar_inactive_color=(0.35, 0.40, 0.48, 0.6),
        )

        self.chat_view = TextInput(
            text="",
            readonly=True,
            multiline=True,
            cursor_blink=False,
            font_size=text_font(),
            size_hint=(1, None),
            padding=(padding_size(), padding_size()),
            background_color=(0.025, 0.03, 0.05, 1),
            foreground_color=(0.92, 0.92, 0.92, 1),
            selection_color=(0.20, 0.45, 0.75, 0.65),
            hint_text=(
                "No topic selected.\n\n"
                "Type a topic below and press Start Brainstorm, "
                "or open Past Sessions to reopen one you've already started."
            ),
            hint_text_color=(0.45, 0.55, 0.68, 0.9),
            use_bubble=True,
            use_handles=True,
        )
        self.chat_view.bind(
            text=lambda inst, val: Clock.schedule_once(self._resize_chat_view, 0)
        )
        # Set the real initial text as a separate assignment AFTER
        # construction, not as a constructor kwarg alongside hint_text.
        # Kivy has a known quirk where hint_text can get visually
        # "stuck" showing even once text is set, if both are passed to
        # the constructor together -- a plain assignment afterward
        # avoids it and forces a proper refresh.
        self.chat_view.text = self.render_transcript_text()

        self.chat_scroll.add_widget(self.chat_view)
        root.add_widget(self.chat_scroll)
        Clock.schedule_once(self._resize_chat_view, 0)

        copy_row = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, 0.06),
        )

        self.copy_btn = Button(
            text="Copy Transcript",
            font_size=button_font(),
            background_normal="",
            background_color=(0.25, 0.28, 0.38, 1),
        )
        self.copy_btn.bind(on_press=self.copy_transcript)
        copy_row.add_widget(self.copy_btn)

        root.add_widget(copy_row)

        # ---------------------------------------------------------
        # Topic input
        # ---------------------------------------------------------
        self.topic_input = TextInput(
            hint_text="Describe the problem you want ChatGPT and Claude to solve...",
            font_size=input_font(),
            multiline=True,
            size_hint=(1, 0.14),
            padding=(padding_size(), padding_size()),
        )
        root.add_widget(self.topic_input)

        control_row = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, 0.08),
        )

        self.start_btn = Button(
            text="Start Brainstorm",
            font_size=button_font(),
            background_normal="",
            background_color=(0.10, 0.40, 0.30, 1),
        )
        self.start_btn.bind(on_press=self.start_brainstorm)
        self._bind_disabled_dim(self.start_btn, (0.10, 0.40, 0.30, 1))
        control_row.add_widget(self.start_btn)

        self.stop_btn = Button(
            text="Stop",
            font_size=button_font(),
            background_normal="",
            background_color=(0.42, 0.22, 0.22, 1),
            disabled=True,
        )
        self.stop_btn.bind(on_press=self.stop_brainstorm)
        self._bind_disabled_dim(self.stop_btn, (0.42, 0.22, 0.22, 1))
        control_row.add_widget(self.stop_btn)

        self.new_topic_btn = Button(
            text="New Topic",
            font_size=button_font(),
            size_hint_x=0.32,
            background_normal="",
            background_color=(0.30, 0.30, 0.14, 1),
        )
        self.new_topic_btn.bind(on_press=self.new_topic)
        self._bind_disabled_dim(self.new_topic_btn, (0.30, 0.30, 0.14, 1))
        control_row.add_widget(self.new_topic_btn)

        self.past_sessions_btn = Button(
            text="Past Sessions",
            font_size=button_font(),
            size_hint_x=0.36,
            background_normal="",
            background_color=(0.16, 0.24, 0.34, 1),
        )
        self.past_sessions_btn.bind(on_press=self.open_past_sessions)
        self._bind_disabled_dim(self.past_sessions_btn, (0.16, 0.24, 0.34, 1))
        control_row.add_widget(self.past_sessions_btn)

        root.add_widget(control_row)

        self.final_decision_btn = Button(
            text="Get Final Decision Now",
            font_size=button_font(),
            size_hint=(1, 0.07),
            background_normal="",
            background_color=(0.42, 0.32, 0.10, 1),
        )
        self.final_decision_btn.bind(on_press=self.request_final_decision)
        self._bind_disabled_dim(self.final_decision_btn, (0.42, 0.32, 0.10, 1))
        root.add_widget(self.final_decision_btn)

        # ---------------------------------------------------------
        # User answer (shown only while an AI is waiting on the user)
        # ---------------------------------------------------------
        self.answer_row = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, 0.10),
        )

        self.answer_input = TextInput(
            hint_text="An AI is waiting for your answer...",
            font_size=input_font(),
            multiline=False,
            disabled=True,
        )
        self._bind_disabled_dim(
            self.answer_input, (1, 1, 1, 1), disabled_color=(0.45, 0.45, 0.48, 1)
        )
        self.answer_row.add_widget(self.answer_input)

        self.answer_btn = Button(
            text="Answer",
            font_size=button_font(),
            size_hint_x=0.28,
            background_normal="",
            background_color=(0.20, 0.32, 0.72, 1),
            disabled=True,
        )
        self.answer_btn.bind(on_press=self.send_user_answer)
        self._bind_disabled_dim(self.answer_btn, (0.20, 0.32, 0.72, 1))
        self.answer_row.add_widget(self.answer_btn)

        root.add_widget(self.answer_row)

        # ---------------------------------------------------------
        # Status
        # ---------------------------------------------------------
        self.status_panel = BoxLayout(
            size_hint=(1, 0.06),
            padding=(spacing_size(), spacing_size()),
        )

        with self.status_panel.canvas.before:
            Color(0.10, 0.16, 0.26, 1)
            self._status_bg_rect = Rectangle(
                pos=self.status_panel.pos, size=self.status_panel.size
            )

        self.status_panel.bind(
            pos=lambda inst, val: setattr(self._status_bg_rect, "pos", val),
            size=lambda inst, val: setattr(self._status_bg_rect, "size", val),
        )

        self.status_label = Label(
            text="Ready.",
            font_size=button_font(),
            bold=True,
            color=(1, 0.85, 0.35, 1),
            halign="center",
            valign="middle",
        )
        self.status_label.bind(
            size=lambda inst, val: setattr(inst, "text_size", val)
        )
        self.status_panel.add_widget(self.status_label)
        root.add_widget(self.status_panel)

        self.add_widget(root)
        self.refresh_topic_title()
        self.refresh_final_decision_button()

    def get_system_status_text(self):
        if self.manager and self.manager.has_screen("home"):
            home = self.manager.get_screen("home")
            provider = getattr(home, "get_system_status_text", None)
            if callable(provider):
                return provider()
        return "WiFi"

    # -------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------
    def load_session(self):
        try:
            if SESSION_FILE.exists():
                data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
                self.transcript = [tuple(entry) for entry in data.get("transcript", [])]
                self.turn_index = int(data.get("turn_index", 0))
                self.pending_solution = None
                self.final_decision = data.get("final_decision")
                self.custom_title = data.get("custom_title")
                return

            # One-time migration from the older plain-text format.
            if LEGACY_SESSION_FILE.exists():
                saved = LEGACY_SESSION_FILE.read_text(encoding="utf-8").strip()
                self.transcript = self._parse_transcript(saved)
                # Best-effort: approximate turn_index from how many AI
                # replies exist. This can drift by one if the legacy
                # session was paused mid-question, but resuming will
                # self-correct after the next successful reply.
                self.turn_index = sum(
                    1 for speaker, _ in self.transcript if speaker in ("ChatGPT", "Claude")
                )
                self.final_decision = None
                self.custom_title = None
                self._last_archived_transcript = None

        except Exception as error:
            print(f"Brainstorm session load error: {type(error).__name__}: {error}")
            self.transcript = []
            self.turn_index = 0
            self.pending_solution = None
            self.final_decision = None
            self.custom_title = None
            self._last_archived_transcript = None

    @staticmethod
    def _parse_transcript(text):
        blocks = text.split("\n\n") if text else []
        transcript = []
        for block in blocks:
            if ":\n" not in block:
                continue
            speaker, _, message = block.partition(":\n")
            transcript.append((speaker.strip(), message))
        return transcript

    def schedule_save(self, delay=0.2):
        if self._save_event is not None:
            self._save_event.cancel()
        self._save_event = Clock.schedule_once(self.save_session, delay)

    def _session_data(self):
        return {
            "turn_index": self.turn_index,
            "transcript": [list(entry) for entry in self.transcript],
            "final_decision": self.final_decision,
            "custom_title": self.custom_title,
        }

    def save_session(self, dt=0):
        self._save_event = None
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp = SESSION_FILE.with_suffix(".tmp")
            temp.write_text(
                json.dumps(self._session_data(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp.replace(SESSION_FILE)
        except Exception as error:
            print(f"Brainstorm session save error: {type(error).__name__}: {error}")

    def render_transcript_text(self):
        """
        Render with a clear visual separator and a running turn counter
        for each AI reply, so a long back-and-forth is easy to scan
        instead of one undifferentiated wall of text.
        """
        lines = []
        ai_turn_number = 0

        for speaker, message in self.transcript:
            if speaker in ("ChatGPT", "Claude"):
                ai_turn_number += 1
                header = f"{'=' * 8} {speaker.upper()}  (turn {ai_turn_number}/{self.turn_budget_end}) {'=' * 8}"
            else:
                header = f"{'-' * 8} {speaker.upper()} {'-' * 8}"

            lines.append(f"{header}\n{message}")

        return "\n\n".join(lines)

    def session_title(self):
        """User-renamed title if set, else the first 'You' message,
        trimmed, used as a label for archives."""
        if self.custom_title:
            return self.custom_title

        for speaker, text in self.transcript:
            if speaker == "You" and text.strip():
                trimmed = text.strip().replace("\n", " ")
                return trimmed[:60] + ("..." if len(trimmed) > 60 else "")
        return "(untitled topic)"

    def refresh_topic_title(self):
        """Keep the always-visible title bar in sync with the current
        topic, since it lives outside the scrollable transcript."""
        if not hasattr(self, "topic_title_label"):
            return

        self.topic_title_label.text = (
            self.session_title() if self.transcript else "No active topic"
        )

    def refresh_final_decision_button(self):
        """Get Final Decision Now should only be pressable while a
        discussion is actively running -- not just while a topic
        happens to exist but is sitting idle."""
        if not hasattr(self, "final_decision_btn"):
            return

        self.final_decision_btn.disabled = not self.running

    def archive_current_session(self):
        """
        Save the current discussion to data/brainstorm/archive/ instead
        of losing it, so New Topic never silently deletes anything.
        """
        if not self.transcript:
            return None

        try:
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"session_{timestamp}.json"
            path = ARCHIVE_DIR / filename

            data = self._session_data()
            data["title"] = self.session_title()
            data["archived_at"] = datetime.now().isoformat(timespec="seconds")

            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._last_archived_transcript = list(self.transcript)
            return path

        except Exception as error:
            print(f"Brainstorm archive error: {type(error).__name__}: {error}")
            return None

    def _archive_current_session_if_changed(self):
        """
        Auto-archive the current session before switching away from it,
        but ONLY if it actually differs from the last time it was
        archived. Without this check, repeatedly viewing/loading other
        past sessions while one stays active would silently create a
        new near-duplicate archive copy every single time.
        """
        if not self.transcript:
            return None

        if list(self.transcript) == self._last_archived_transcript:
            return None

        return self.archive_current_session()

    @staticmethod
    @staticmethod
    def _transcript_stats(transcript):
        """Return (chatgpt_count, claude_count) for a transcript list."""
        chatgpt_count = sum(1 for speaker, _ in transcript if speaker == "ChatGPT")
        claude_count = sum(1 for speaker, _ in transcript if speaker == "Claude")
        return chatgpt_count, claude_count

    @staticmethod
    def list_archived_sessions():
        """
        Return archived sessions newest-first, each as a dict with
        path, title, archived_at, chatgpt_count, claude_count, and
        final_decision (None if no decision was reached).
        """
        if not ARCHIVE_DIR.exists():
            return []

        entries = []

        for path in ARCHIVE_DIR.glob("session_*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                transcript = data.get("transcript", [])
                chatgpt_count, claude_count = BrainstormScreen._transcript_stats(transcript)

                entries.append(
                    {
                        "path": path,
                        "title": str(data.get("title", path.stem)),
                        "archived_at": str(data.get("archived_at", "")),
                        "chatgpt_count": chatgpt_count,
                        "claude_count": claude_count,
                        "final_decision": data.get("final_decision"),
                    }
                )
            except Exception as error:
                print(f"Brainstorm archive read error ({path.name}): {error}")

        entries.sort(key=lambda item: item["path"].stat().st_mtime, reverse=True)
        return entries

    # -------------------------------------------------------------
    # Transcript UI updates (always called on the main thread)
    # -------------------------------------------------------------
    def _resize_chat_view(self, dt=0):
        """
        Grow the TextInput to fit all of its content, so it never clips
        internally -- all scrolling then happens in the outer
        ScrollView, which is what actually draws the visible scrollbar.
        Falls back to filling the viewport if line metrics aren't
        available yet (e.g. before the first layout pass).
        """
        try:
            line_count = max(1, len(self.chat_view._lines))
            vertical_padding = self.chat_view.padding[1] + self.chat_view.padding[3]
            computed_height = int(line_count * self.chat_view.line_height + vertical_padding)
        except Exception:
            computed_height = 0

        viewport_height = self.chat_scroll.height or 1
        self.chat_view.height = max(computed_height, viewport_height)

    def scroll_to_bottom(self, dt=0):
        self.chat_scroll.scroll_y = 0

    def _refresh_transcript_ui(self, dt=0):
        """
        Update the on-screen transcript and persist it. Safe to call via
        Clock.schedule_once from a worker thread; unlike append_message,
        this does not itself mutate self.transcript, so it can safely
        run asynchronously after a direct transcript.append() elsewhere.
        """
        self.chat_view.text = self.render_transcript_text()
        self.schedule_save()
        Clock.schedule_once(self._resize_chat_view, 0)
        Clock.schedule_once(self.scroll_to_bottom, 0)
        Clock.schedule_once(self.scroll_to_bottom, 0.05)

    def append_message(self, speaker, message):
        self.transcript.append((speaker, str(message)))
        self._refresh_transcript_ui()
        self.refresh_topic_title()
        self.refresh_final_decision_button()

    def copy_transcript(self, instance=None):
        """
        Copy selected text, or the full transcript when nothing is
        selected. Mirrors AIScreen.copy_chat_text so error text (like a
        Claude 400 response body) can always be pulled out and shared.
        """
        selected = ""

        try:
            selected = str(self.chat_view.selection_text).strip()
        except Exception:
            selected = ""

        text_to_copy = selected if selected else self.render_transcript_text()

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

            self.set_status(
                "Selected text copied" if selected else "Transcript copied"
            )

        except Exception as error:
            self.set_status(f"Copy failed: {type(error).__name__}: {error}")

    def set_status(self, text):
        self.status_label.text = str(text)

    # -------------------------------------------------------------
    # Start / Stop
    # -------------------------------------------------------------
    def _recover_if_thread_died(self):
        """
        Self-heal from a stuck 'running' state.

        If self.running is True but the background thread is no longer
        alive (e.g. it crashed without reaching finish_brainstorm due to
        a bug, or the app state got out of sync some other way), the
        Start/Stop/Get Final Decision buttons would otherwise stay
        permanently disabled or silently no-op forever. Detect that and
        reset to a clean idle state so the user can just try again.
        """
        if not self.running:
            return False

        if self.debate_thread is not None and self.debate_thread.is_alive():
            return False

        self.running = False
        self.start_btn.disabled = False
        self.stop_btn.disabled = True
        self.new_topic_btn.disabled = False
        self.past_sessions_btn.disabled = False
        self.refresh_final_decision_button()
        self.set_status(
            "Recovered from a stalled discussion. Press Start/Continue again."
        )
        return True

    def start_brainstorm(self, instance=None):
        """
        Start a new topic, or resume an interrupted/paused discussion.

        If a transcript already exists (from a previous error, Stop, or a
        session reloaded from disk), pressing this button CONTINUES that
        discussion instead of discarding it. Any text typed in the topic
        box is added as an extra note from you before resuming. Use
        "New Topic" to explicitly start over from a blank transcript.
        """
        self._recover_if_thread_died()

        if self.running:
            return

        if not self.chatgpt_client.has_key():
            self.set_status("OpenAI API key not configured. See Settings.")
            return

        if not self.claude_client.has_key():
            self.set_status("Claude API key not configured. See Settings.")
            return

        typed_text = self.topic_input.text.strip()

        if self.transcript:
            # Resume an existing discussion. Do not touch turn_index or
            # clear the transcript -- that would throw away everything
            # the two AIs (and you) have already established.
            if typed_text:
                self.append_message("You", typed_text)
                self.topic_input.text = ""

            self.set_status("Resuming the discussion...")

        else:
            if not typed_text:
                self.set_status("Enter a problem or idea first.")
                return

            self.turn_index = 0
            self.pending_solution = None
            self.final_decision = None
            self.custom_title = None
            self._last_archived_transcript = None
            self.append_message("You", typed_text)
            self.topic_input.text = ""
            self.set_status("ChatGPT and Claude are discussing your problem...")

        self.running = True
        self.stop_requested = False
        self.waiting_for_user = False
        self.pause_event.clear()
        self.turn_budget_end = self.turn_index + MAX_TURNS

        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        self.new_topic_btn.disabled = True
        self.past_sessions_btn.disabled = True
        self.refresh_final_decision_button()

        self.debate_thread = threading.Thread(
            target=self.run_debate_loop,
            daemon=True,
        )
        self.debate_thread.start()

    def new_topic(self, instance=None):
        """
        Archive the current discussion (if any) and start fresh.

        If you've already typed a topic in the box, this archives the
        old discussion AND immediately starts the new one in a single
        click -- matching "type a topic, press New Topic" as one
        action, rather than requiring a separate Start Brainstorm press
        afterward. If the box is empty, it just clears the screen and
        waits for you to type something.

        Nothing is ever silently deleted: the outgoing discussion is
        saved under data/brainstorm/archive/ and can be reopened later
        from "Past Sessions" -- unless it's identical to the last
        archive already made of it (e.g. you just reloaded that same
        archive and changed nothing), in which case no redundant copy
        is created.
        """
        if self.running:
            self.set_status("Stop the current discussion first.")
            return

        if not self.chatgpt_client.has_key():
            self.set_status("OpenAI API key not configured. See Settings.")
            return

        if not self.claude_client.has_key():
            self.set_status("Claude API key not configured. See Settings.")
            return

        typed_text = self.topic_input.text.strip()

        archived_path = self._archive_current_session_if_changed()

        self.transcript = []
        self.turn_index = 0
        self.pending_solution = None
        self.final_decision = None
        self.custom_title = None
        self._last_archived_transcript = None
        self.chat_view.text = ""
        self.start_btn.text = "Start Brainstorm"
        self.refresh_topic_title()
        self.refresh_final_decision_button()

        # Clear the active session file too, now that its content lives
        # safely in the archive.
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink()
        except OSError:
            pass

        if not typed_text:
            if archived_path is not None:
                self.set_status("Previous discussion archived. Ready for a new topic.")
            else:
                self.set_status("Ready for a new topic.")
            return

        # A topic was already typed -- start it immediately instead of
        # requiring a second Start Brainstorm click.
        self.topic_input.text = ""
        self.append_message("You", typed_text)

        self.running = True
        self.stop_requested = False
        self.waiting_for_user = False
        self.pause_event.clear()
        self.turn_budget_end = MAX_TURNS
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        self.new_topic_btn.disabled = True
        self.past_sessions_btn.disabled = True
        self.refresh_final_decision_button()

        if archived_path is not None:
            self.set_status("Previous discussion archived. Starting new topic...")
        else:
            self.set_status("ChatGPT and Claude are discussing your problem...")

        self.debate_thread = threading.Thread(
            target=self.run_debate_loop,
            daemon=True,
        )
        self.debate_thread.start()

    # -------------------------------------------------------------
    # Past Sessions
    # -------------------------------------------------------------
    def open_past_sessions(self, instance=None):
        if self.running:
            self.set_status("Stop the current discussion first.")
            return

        # Unified list: the currently active discussion (if any) plus
        # every archived one, newest first.
        rows = []

        if self.transcript:
            chatgpt_count, claude_count = self._transcript_stats(self.transcript)
            rows.append(
                {
                    "path": None,
                    "title": self.session_title(),
                    "archived_at": "Current session",
                    "chatgpt_count": chatgpt_count,
                    "claude_count": claude_count,
                    "final_decision": self.final_decision,
                    "is_current": True,
                }
            )

        for entry in self.list_archived_sessions():
            entry["is_current"] = False
            rows.append(entry)

        content = BoxLayout(orientation="vertical", spacing=spacing_size(), padding=padding_size())

        if not rows:
            content.add_widget(
                Label(
                    text="No topics yet. Start a discussion to see it here.",
                    font_size=text_font(),
                    halign="center",
                    valign="middle",
                )
            )
        else:
            scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False, do_scroll_y=True)
            session_list = GridLayout(cols=1, spacing=spacing_size(), size_hint_y=None)
            session_list.bind(minimum_height=session_list.setter("height"))

            popup_holder = {}

            for row_data in rows:
                session_list.add_widget(
                    self._build_past_session_row(row_data, popup_holder)
                )

            scroll.add_widget(session_list)
            content.add_widget(scroll)

        close_btn = Button(
            text="Close",
            font_size=button_font(),
            size_hint=(1, None),
            height=button_height(),
            background_normal="",
            background_color=(0.30, 0.30, 0.14, 1),
        )
        content.add_widget(close_btn)

        popup = Popup(
            title="Past Sessions",
            content=content,
            size_hint=(0.9, 0.85),
        )
        close_btn.bind(on_press=popup.dismiss)

        if rows:
            popup_holder["popup"] = popup

        popup.open()

    def _build_past_session_row(self, row_data, popup_holder):
        """Build one row (info button + stats + action buttons) for the
        Past Sessions popup, for either the current session or an
        archived one."""
        path = row_data["path"]
        is_current = row_data["is_current"]
        decided = row_data["final_decision"] is not None

        decision_text = "Decision: Reached" if decided else "Decision: Not yet"
        label_text = (
            f"{row_data['archived_at']}\n{row_data['title']}\n"
            f"ChatGPT: {row_data['chatgpt_count']}  |  "
            f"Claude: {row_data['claude_count']}  |  {decision_text}"
        )

        # Current topic wins regardless of decision status (green); a
        # decided topic is blue; still-undecided is yellow/gold, so the
        # whole list is scannable at a glance.
        if is_current:
            row_color = (0.14, 0.42, 0.20, 1)
        elif decided:
            row_color = (0.12, 0.22, 0.46, 1)
        else:
            row_color = (0.48, 0.40, 0.08, 1)

        row = BoxLayout(orientation="vertical", spacing=spacing_size(), size_hint_y=None)
        row.bind(minimum_height=row.setter("height"))

        info_btn = Button(
            text=label_text,
            font_size=small_font(),
            size_hint_y=None,
            height=row_height(),
            halign="left",
            valign="middle",
            background_normal="",
            background_color=row_color,
        )
        info_btn.bind(
            size=lambda inst, val: setattr(
                inst, "text_size", (val[0] - spacing_size() * 2, val[1])
            )
        )

        if is_current:
            info_btn.bind(on_press=lambda inst: popup_holder["popup"].dismiss())
        else:
            info_btn.bind(
                on_press=lambda inst, p=path: self.load_archived_session(
                    p, popup_holder.get("popup")
                )
            )

        row.add_widget(info_btn)

        actions = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint_y=None,
            height=small_row_height(),
        )

        if decided:
            view_btn = Button(
                text="View Decision",
                font_size=button_font(),
                background_normal="",
                background_color=(0.14, 0.30, 0.42, 1),
            )
            view_btn.bind(
                on_press=lambda inst, d=row_data: self._show_decision_popup(
                    "Final decision:", d["final_decision"], title=d["title"]
                )
            )
            actions.add_widget(view_btn)
        else:
            get_btn = Button(
                text="Get Decision",
                font_size=button_font(),
                background_normal="",
                background_color=(0.42, 0.32, 0.10, 1),
            )
            get_btn.bind(
                on_press=lambda inst, p=path, cur=is_current: self._get_decision_for_row(
                    p, cur, popup_holder.get("popup")
                )
            )
            actions.add_widget(get_btn)

        rename_btn = Button(
            text="Rename",
            font_size=button_font(),
            size_hint_x=0.4,
            background_normal="",
            background_color=(0.30, 0.30, 0.14, 1),
        )
        rename_btn.bind(
            on_press=lambda inst, d=row_data: self.open_rename_popup(
                d, popup_holder.get("popup")
            )
        )
        actions.add_widget(rename_btn)

        if not is_current:
            delete_btn = Button(
                text="Delete",
                font_size=button_font(),
                size_hint_x=0.4,
                background_normal="",
                background_color=(0.42, 0.18, 0.18, 1),
            )
            delete_btn.bind(
                on_press=lambda inst, p=path: self.confirm_delete_session(
                    p, popup_holder.get("popup")
                )
            )
            actions.add_widget(delete_btn)

        row.add_widget(actions)
        return row

    def open_rename_popup(self, row_data, past_sessions_popup=None):
        content = BoxLayout(orientation="vertical", spacing=spacing_size(), padding=padding_size())

        content.add_widget(
            Label(
                text="Rename topic:",
                font_size=text_font(),
                bold=True,
                size_hint=(1, 0.25),
            )
        )

        title_input = TextInput(
            text=row_data["title"],
            font_size=input_font(),
            multiline=False,
            size_hint=(1, 0.35),
        )
        content.add_widget(title_input)

        buttons = BoxLayout(orientation="horizontal", spacing=spacing_size(), size_hint=(1, 0.35))

        cancel_btn = Button(
            text="Cancel",
            font_size=button_font(),
            background_normal="",
            background_color=(0.18, 0.28, 0.42, 1),
        )
        save_btn = Button(
            text="Save",
            font_size=button_font(),
            background_normal="",
            background_color=(0.10, 0.40, 0.30, 1),
        )
        buttons.add_widget(cancel_btn)
        buttons.add_widget(save_btn)
        content.add_widget(buttons)

        rename_popup = Popup(
            title="",
            content=content,
            size_hint=(0.85, 0.35),
            auto_dismiss=False,
        )

        cancel_btn.bind(on_release=rename_popup.dismiss)
        save_btn.bind(
            on_release=lambda *_: self._save_renamed_session(
                row_data["path"],
                row_data["is_current"],
                title_input.text,
                rename_popup,
                past_sessions_popup,
            )
        )

        rename_popup.open()

    def _save_renamed_session(self, path, is_current, new_title, rename_popup, past_sessions_popup):
        rename_popup.dismiss()

        new_title = new_title.strip()

        if not new_title:
            self.set_status("Title cannot be empty.")
            return

        if is_current:
            self.custom_title = new_title
            self.refresh_topic_title()
            self.refresh_final_decision_button()
            self.schedule_save()
        else:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                data["title"] = new_title
                path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as error:
                self.set_status(f"Rename failed: {type(error).__name__}: {error}")
                return

        self.set_status("Topic renamed.")

        # Refresh the Past Sessions list so the new title is visible.
        if past_sessions_popup is not None:
            past_sessions_popup.dismiss()
        self.open_past_sessions()

    def _get_decision_for_row(self, path, is_current, popup=None):
        """
        'Get Decision' pressed on a Past Sessions row. For the current
        session, force a final decision immediately. For an archived
        one, load it as the active session first, then force it.
        """
        if popup is not None:
            popup.dismiss()

        if not is_current:
            self.load_archived_session(path)

        self.request_final_decision()

    def load_archived_session(self, path, popup=None):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:
            self.set_status(f"Could not load session: {type(error).__name__}: {error}")
            if popup is not None:
                popup.dismiss()
            return

        # Anything currently on screen is archived first, so switching
        # to a past session never loses the one you were just having --
        # but only if it actually changed since the last time it was
        # archived, to avoid creating a silent duplicate copy.
        self._archive_current_session_if_changed()

        # The archive being loaded now becomes "the current session" --
        # remove the archive file itself so it doesn't sit alongside the
        # now-live copy looking like a duplicate. If you switch away
        # again later, it will be re-archived fresh at that point.
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            print(f"Brainstorm: could not remove loaded archive {path.name}: {error}")

        self.transcript = [tuple(entry) for entry in data.get("transcript", [])]
        self.turn_index = int(data.get("turn_index", 0))
        self.pending_solution = None
        self.final_decision = data.get("final_decision")
        # Carry the archive's title forward as the resumed session's
        # title (whether it was auto-derived or renamed at archive
        # time), so it doesn't unexpectedly change once resumed.
        self.custom_title = data.get("title")
        # The archive file was just deleted above (it's now represented
        # by "current" instead), so there is NO backing file anymore --
        # do NOT mark this as "already archived", or switching away
        # later without any changes would skip re-archiving it (dedup
        # logic) and this topic would vanish entirely. Setting this to
        # None forces exactly one fresh archive on the next switch-away.
        self._last_archived_transcript = None
        self.chat_view.text = self.render_transcript_text()
        self.start_btn.text = "Continue Brainstorm" if self.transcript else "Start Brainstorm"
        self.refresh_topic_title()
        self.refresh_final_decision_button()
        self.schedule_save()

        Clock.schedule_once(self.scroll_to_bottom, 0.05)
        self.set_status(f"Loaded: {data.get('title', path.stem)}")

        if popup is not None:
            popup.dismiss()

    def confirm_delete_session(self, path, past_sessions_popup=None):
        """Show a Yes/Cancel confirmation before permanently deleting an
        archived session."""
        content = BoxLayout(orientation="vertical", spacing=spacing_size(), padding=padding_size())

        content.add_widget(
            Label(
                text="Delete this session?\nThis cannot be undone.",
                font_size=text_font(),
                bold=True,
                halign="center",
                valign="middle",
            )
        )

        buttons = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, 0.4),
        )

        cancel_btn = Button(
            text="Cancel",
            font_size=button_font(),
            background_normal="",
            background_color=(0.18, 0.28, 0.42, 1),
        )
        yes_btn = Button(
            text="Yes, Delete",
            font_size=button_font(),
            background_normal="",
            background_color=(0.55, 0.16, 0.16, 1),
        )

        buttons.add_widget(cancel_btn)
        buttons.add_widget(yes_btn)
        content.add_widget(buttons)

        confirm_popup = Popup(
            title="",
            content=content,
            size_hint=(0.7, 0.32),
            auto_dismiss=False,
        )

        cancel_btn.bind(on_release=confirm_popup.dismiss)
        yes_btn.bind(
            on_release=lambda *_: self._do_delete_session(
                path, confirm_popup, past_sessions_popup
            )
        )

        confirm_popup.open()

    def _do_delete_session(self, path, confirm_popup, past_sessions_popup):
        confirm_popup.dismiss()

        try:
            path.unlink(missing_ok=True)
            self.set_status("Session deleted.")
        except OSError as error:
            self.set_status(f"Delete failed: {type(error).__name__}: {error}")

        # Refresh the Past Sessions list so the deleted row disappears.
        if past_sessions_popup is not None:
            past_sessions_popup.dismiss()
        self.open_past_sessions()

    def request_final_decision(self, instance=None):
        """
        Force the discussion toward a concrete conclusion right now,
        instead of waiting for the AIs to decide to converge on their
        own or hitting MAX_TURNS with nothing resolved.
        """
        self._recover_if_thread_died()

        if not self.transcript:
            self.set_status("Start a discussion first.")
            return

        if self.waiting_for_user:
            self.set_status("Answer the pending question first.")
            return

        if self.running:
            # A turn is already in flight; the loop picks this up at the
            # top of its next iteration (see run_debate_loop).
            self.pending_final_decision = True
            self.set_status("Will ask for a final decision after this turn.")
            return

        # Idle: resume immediately with the forcing note, reusing the
        # same "continue an existing discussion" path as Start/Continue.
        self.append_message("You", FINAL_DECISION_PROMPT)

        self.running = True
        self.stop_requested = False
        self.pause_event.clear()
        self.turn_budget_end = self.turn_index + MAX_TURNS
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        self.new_topic_btn.disabled = True
        self.past_sessions_btn.disabled = True
        self.refresh_final_decision_button()
        self.set_status("Asking ChatGPT and Claude for a final decision...")

        self.debate_thread = threading.Thread(target=self.run_debate_loop, daemon=True)
        self.debate_thread.start()

    def stop_brainstorm(self, instance=None):
        self.stop_requested = True

        # Unblock the loop if it is currently waiting on a user answer.
        if self.waiting_for_user:
            self.waiting_for_user = False
            self.pause_event.set()

        Clock.schedule_once(lambda dt: self.set_status("Stopping..."), 0)

    def finish_brainstorm(self, final_status):
        self.running = False
        self.start_btn.disabled = False
        self.start_btn.text = "Continue Brainstorm" if self.transcript else "Start Brainstorm"
        self.stop_btn.disabled = True
        self.new_topic_btn.disabled = False
        self.past_sessions_btn.disabled = False
        self.refresh_final_decision_button()
        self.answer_input.disabled = True
        self.answer_btn.disabled = True
        self.answer_input.hint_text = "An AI is waiting for your answer..."
        self.set_status(final_status)

    # -------------------------------------------------------------
    # User answers a mid-brainstorm question
    # -------------------------------------------------------------
    def send_user_answer(self, instance=None):
        if not self.waiting_for_user:
            return

        answer = self.answer_input.text.strip()

        if not answer:
            return

        self.answer_input.text = ""
        self.answer_input.disabled = True
        self.answer_btn.disabled = True
        self.waiting_for_user = False

        self.append_message("You", answer)
        self.set_status("ChatGPT and Claude are continuing...")

        self.pause_event.set()

    # -------------------------------------------------------------
    # Debate loop (runs on a background thread)
    # -------------------------------------------------------------
    @staticmethod
    def _extract_after_marker(text, marker):
        """
        Return everything after `marker` (case-insensitive) if it
        appears anywhere in `text`, else None. Used instead of
        str.startswith() because the AIs sometimes write a short
        lead-in sentence before writing "SOLUTION:" or
        "QUESTION_FOR_USER:", and a strict startswith() check misses
        the marker entirely in that case.
        """
        upper_text = text.upper()
        index = upper_text.find(marker)

        if index == -1:
            return None

        return text[index + len(marker):].strip()

    @staticmethod
    def _build_messages(transcript, self_name):
        """
        Convert the shared transcript into a role-tagged message list
        for one AI's point of view. Consecutive messages from the same
        side are merged, since some providers (Claude) require strict
        user/assistant alternation.
        """
        merged = []

        for speaker, text in transcript:
            role = "assistant" if speaker == self_name else "user"
            label = "" if speaker == self_name else f"[{speaker}]: "
            content = f"{label}{text}"

            if merged and merged[-1]["role"] == role:
                merged[-1]["content"] += "\n\n" + content
            else:
                merged.append({"role": role, "content": content})

        # Anthropic requires the first message to have role "user".
        if merged and merged[0]["role"] != "user":
            merged.insert(0, {"role": "user", "content": "(conversation start)"})

        # Anthropic also rejects a request that ends on role "assistant"
        # ("assistant message prefill" is not supported for this call
        # shape). This can happen right after a pause/resume if the
        # transcript's last entry happens to be this AI's own turn.
        if merged and merged[-1]["role"] != "user":
            merged.append({"role": "user", "content": "Please continue."})

        return merged

    def run_debate_loop(self):
        speakers = ["ChatGPT", "Claude"]

        while self.turn_index < self.turn_budget_end:
            if self.stop_requested:
                Clock.schedule_once(
                    lambda dt: self.finish_brainstorm("Stopped."), 0
                )
                return

            if self.pending_final_decision:
                self.pending_final_decision = False
                # Mutate the transcript directly (synchronously) so the
                # very next _build_messages() call below already sees
                # this note -- Clock.schedule_once alone would only
                # queue the UI update for later, racing the API call.
                self.transcript.append(("You", FINAL_DECISION_PROMPT))
                Clock.schedule_once(self._refresh_transcript_ui, 0)

            speaker = speakers[self.turn_index % 2]

            Clock.schedule_once(
                lambda dt, s=speaker, n=self.turn_index + 1: self.set_status(
                    f"Turn {n}/{self.turn_budget_end}: waiting for {s}..."
                ),
                0,
            )

            try:
                if speaker == "ChatGPT":
                    messages = self._build_messages(self.transcript, "ChatGPT")
                    reply = self.chatgpt_client.send(
                        system=CHATGPT_SYSTEM_PROMPT,
                        messages=messages,
                    )
                else:
                    messages = self._build_messages(self.transcript, "Claude")
                    reply = self.claude_client.send(
                        system=CLAUDE_SYSTEM_PROMPT,
                        messages=messages,
                    )

            except (ChatGPTClientError, ClaudeClientError) as error:
                Clock.schedule_once(
                    lambda dt, s=speaker, e=error: self._handle_turn_error(s, e),
                    0,
                )
                return

            except Exception as error:
                Clock.schedule_once(
                    lambda dt, s=speaker, e=error: self._handle_turn_error(s, e),
                    0,
                )
                return

            reply_stripped = reply.strip()
            upper_reply = reply_stripped.upper()

            # Search for the marker anywhere in the reply, not just at the
            # very start -- both AIs sometimes write a lead-in sentence
            # before "SOLUTION:"/"QUESTION_FOR_USER:", and a strict
            # startswith() check silently misses those every time.
            question = self._extract_after_marker(reply_stripped, "QUESTION_FOR_USER:")

            if question is not None:
                Clock.schedule_once(
                    lambda dt, s=speaker, q=question: self._handle_question(s, q),
                    0,
                )

                self.waiting_for_user = True
                self.pause_event.clear()
                self.pause_event.wait()

                if self.stop_requested:
                    Clock.schedule_once(
                        lambda dt: self.finish_brainstorm("Stopped."), 0
                    )
                    return

                # Do not advance turn_index here: the same speaker that
                # asked continues, now with the user's answer available.
                continue

            Clock.schedule_once(
                lambda dt, s=speaker, r=reply_stripped: self.append_message(s, r),
                0,
            )

            other_speaker = "Claude" if speaker == "ChatGPT" else "ChatGPT"

            # AGREED: explicit confirmation of the other AI's pending
            # proposal -> finalize immediately.
            agreement = self._extract_after_marker(reply_stripped, "AGREED:")

            if agreement is not None and self.pending_solution and self.pending_solution["speaker"] == other_speaker:
                final_text = agreement or self.pending_solution["text"]
                self.pending_solution = None

                Clock.schedule_once(
                    lambda dt, sol=final_text: self._announce_solution(
                        "ChatGPT and Claude", sol
                    ),
                    0,
                )
                return

            solution = self._extract_after_marker(reply_stripped, "SOLUTION:")

            if solution is not None:
                if self.pending_solution and self.pending_solution["speaker"] == other_speaker:
                    # The other AI already proposed a solution and this
                    # speaker independently proposed one too -- treat
                    # that as convergence and finalize with both.
                    combined = (
                        f"{self.pending_solution['speaker']}'s proposal:\n"
                        f"{self.pending_solution['text']}\n\n"
                        f"{speaker}'s proposal:\n{solution}\n\n"
                        "Both AIs converged on this solution."
                    )
                    self.pending_solution = None

                    Clock.schedule_once(
                        lambda dt, sol=combined: self._announce_solution(
                            "ChatGPT and Claude", sol
                        ),
                        0,
                    )
                    return

                # First proposal on the table -- record it and let the
                # OTHER AI respond next, rather than finalizing solo.
                self.pending_solution = {"speaker": speaker, "text": solution}
                self.turn_index += 1
                continue

            self.turn_index += 1

        Clock.schedule_once(
            lambda dt: self.finish_brainstorm(
                "Reached the maximum number of turns without a final solution."
            ),
            0,
        )

    def _announce_solution(self, speaker, solution_text):
        """
        Called once both AIs have converged on a final decision (see the
        AGREED:/SOLUTION: handshake in run_debate_loop). Stores the
        decision so it's visible later from Past Sessions, then shows a
        hard-to-miss popup on top of the quiet status-bar update.
        """
        self.final_decision = solution_text
        self.schedule_save()
        self.finish_brainstorm(f"Solution reached (by {speaker}).")
        self._show_decision_popup(f"{speaker} proposed a solution:", solution_text)

    @staticmethod
    def _show_decision_popup(heading, decision_text, title="Solution Reached"):
        content = BoxLayout(orientation="vertical", spacing=spacing_size(), padding=padding_size())

        content.add_widget(
            Label(
                text=heading,
                font_size=text_font(),
                bold=True,
                size_hint=(1, 0.15),
                halign="center",
                valign="middle",
            )
        )

        scroll = ScrollView(size_hint=(1, 0.65), do_scroll_x=False, do_scroll_y=True)
        solution_label = Label(
            text=decision_text,
            font_size=text_font(),
            size_hint_y=None,
            halign="left",
            valign="top",
        )
        solution_label.bind(
            width=lambda inst, val: setattr(inst, "text_size", (val, None)),
            texture_size=lambda inst, val: setattr(inst, "height", val[1]),
        )
        scroll.add_widget(solution_label)
        content.add_widget(scroll)

        close_btn = Button(
            text="OK",
            font_size=button_font(),
            size_hint=(1, 0.20),
            background_normal="",
            background_color=(0.10, 0.40, 0.30, 1),
        )
        content.add_widget(close_btn)

        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.85, 0.6),
            auto_dismiss=False,
        )
        close_btn.bind(on_press=popup.dismiss)
        popup.open()

    def _handle_question(self, speaker, question):
        self.append_message(speaker, f"QUESTION_FOR_USER: {question}")
        self.answer_input.disabled = False
        self.answer_btn.disabled = False
        self.answer_input.hint_text = f"{speaker} is asking: {question}"
        self.answer_input.focus = True
        self.set_status(f"{speaker} needs more information from you.")

    def _handle_turn_error(self, speaker, error):
        self.append_message(
            speaker,
            f"(error contacting {speaker}: {type(error).__name__}: {error})",
        )
        self.finish_brainstorm(
            f"{speaker} request failed. Fix the issue, then press "
            "Start Brainstorm again to resume from here."
        )

    # -------------------------------------------------------------
    # Lifecycle / navigation
    # -------------------------------------------------------------
    def on_pre_enter(self, *args):
        self.chat_view.text = self.render_transcript_text()
        self.refresh_topic_title()
        self.refresh_final_decision_button()
        if not self.running:
            self.start_btn.text = "Continue Brainstorm" if self.transcript else "Start Brainstorm"

        # Force a resize unconditionally, not just via the text-change
        # bind: if this exact text was already set once before (e.g.
        # loaded at construction time, when the screen wasn't visible
        # yet and had no real size), Kivy won't fire the bound callback
        # for a same-value reassignment above, leaving the widget stuck
        # at whatever bogus tiny height it first computed. Scheduled
        # twice, like scroll_to_bottom below, to catch up after this
        # screen's own layout pass completes now that it's visible.
        Clock.schedule_once(self._resize_chat_view, 0)
        Clock.schedule_once(self._resize_chat_view, 0.05)
        Clock.schedule_once(self.scroll_to_bottom, 0.05)
        Clock.schedule_once(self.scroll_to_bottom, 0.15)

    def on_leave(self, *args):
        self.save_session()

    def go_back(self, instance=None):
        if self.running:
            self.set_status("Stop the brainstorm before leaving.")
            return

        target = self.return_screen

        if not target or not self.manager.has_screen(target):
            target = "home"

        self.manager.current = target