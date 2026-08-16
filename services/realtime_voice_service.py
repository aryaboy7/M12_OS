import asyncio
import base64
import ctypes
import ctypes.util
import json
import os
import queue
import ssl
import certifi
import threading
import time
from pathlib import Path

from kivy.utils import platform as kivy_platform
from openai import AsyncOpenAI

from services.memory_manager import get_memory_manager
from services.api_key_manager import APIKeyManager


IS_ANDROID = kivy_platform == "android"

if IS_ANDROID:
    # python-for-android may not expose Android's system CA store
    # correctly to Python/OpenSSL. Use certifi's bundled CA store.
    ca_bundle = certifi.where()
    os.environ["SSL_CERT_FILE"] = ca_bundle
    os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle

    sd = None
    SOUNDDEVICE_AVAILABLE = False
    SOUNDDEVICE_ERROR = "PortAudio is not used on Android."
else:
    try:
        import sounddevice as sd
        SOUNDDEVICE_AVAILABLE = True
        SOUNDDEVICE_ERROR = ""
    except Exception as error:
        sd = None
        SOUNDDEVICE_AVAILABLE = False
        SOUNDDEVICE_ERROR = (
            f"{type(error).__name__}: {error}"
        )


BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_FILE = BASE_DIR / "config" / "ai_settings.json"

DEFAULT_MODEL = "gpt-realtime-2"
DEFAULT_VOICE = "marin"

SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2
INPUT_CHUNK_MS = 20
INPUT_FRAMES = int(
    SAMPLE_RATE * INPUT_CHUNK_MS / 1000
)

SDL_INIT_AUDIO = 0x00000010
AUDIO_S16LSB = 0x8010


class SDL_AudioSpec(ctypes.Structure):
    _fields_ = [
        ("freq", ctypes.c_int),
        ("format", ctypes.c_uint16),
        ("channels", ctypes.c_uint8),
        ("silence", ctypes.c_uint8),
        ("samples", ctypes.c_uint16),
        ("padding", ctypes.c_uint16),
        ("size", ctypes.c_uint32),
        ("callback", ctypes.c_void_p),
        ("userdata", ctypes.c_void_p),
    ]


class RealtimeVoiceService:
    """
    Standalone OpenAI Realtime speech-to-speech service for M12OS.

    Current responsibilities:
        - Maintain one Realtime WebSocket session.
        - Stream 24 kHz, mono, signed 16-bit PCM microphone audio.
        - Use OpenAI server VAD to detect speech turns.
        - Receive and play streamed 24 kHz PCM speech.
        - Receive response transcripts for the UI.
        - Support English, Russian, and automatic input transcription.
        - Reconnect automatically after network failures.
        - Shut down microphone, speaker, and WebSocket cleanly.

    This file can be tested independently before it is connected to
    screens/ai_screen.py.
    """

    LANGUAGE_NAMES = {
        "en": "English",
        "ru": "Russian",
        "auto": "Automatic",
    }

    def __init__(
        self,
        on_status=None,
        on_user_transcript=None,
        on_text_delta=None,
        on_text_done=None,
        on_speech_started=None,
        on_speech_stopped=None,
        on_local_request=None,
        on_local_answer=None,
        on_error=None,
    ):
        settings = self.load_settings()

        api_key = APIKeyManager.get_api_key()

        if not api_key:
            raise RuntimeError(
                "OpenAI API key is not configured. "
                "Open Settings -> AI Setup."
            )

        self.model = str(
            settings.get(
                "realtime_model",
                DEFAULT_MODEL,
            )
        ).strip() or DEFAULT_MODEL

        self.voice = str(
            settings.get(
                "realtime_voice",
                DEFAULT_VOICE,
            )
        ).strip() or DEFAULT_VOICE

        self.language = self.normalize_language(
            settings.get(
                "voice_language",
                "en",
            )
        )

        self.instructions = str(
            settings.get(
                "realtime_instructions",
                (
                    "You are Ace, the M12 AI assistant. "
                    "Answer only the exact question asked. "
                    "Give a short, direct answer unless the user "
                    "explicitly requests more detail."
                ),
            )
        ).strip()

        self.speaker_echo_protection = bool(
            settings.get(
                "speaker_echo_protection",
                True,
            )
        )

        self.client = AsyncOpenAI(
            api_key=api_key,
            timeout=45.0,
            max_retries=0,
        )

        self.permanent_memory = (
            get_memory_manager()
        )

        self.on_status = on_status
        self.on_user_transcript = (
            on_user_transcript
        )
        self.on_text_delta = on_text_delta
        self.on_text_done = on_text_done
        self.on_speech_started = (
            on_speech_started
        )
        self.on_speech_stopped = (
            on_speech_stopped
        )
        self.on_local_request = on_local_request
        self.on_local_answer = on_local_answer
        self.on_error = on_error

        self._thread = None
        self._loop = None
        self._connection = None

        self._stop_event = threading.Event()
        self._connected_event = (
            threading.Event()
        )
        self._ready_event = threading.Event()
        self._conversation_active = (
            threading.Event()
        )
        self._assistant_speaking = (
            threading.Event()
        )

        self._microphone_enabled = threading.Event()
        self._echo_paused_microphone = False
        self._echo_resume_generation = 0
        self._echo_resume_lock = threading.Lock()

        # Local TTS can already be buffered at the Realtime server when
        # microphone capture is muted. Suppress completed transcripts while
        # local speech is active and briefly after it finishes.
        self._local_echo_suppress_until = 0.0

        self._speaker_timing_lock = threading.Lock()
        self._speaker_playback_until = 0.0

        self._send_queue = None
        self._microphone_queue = queue.Queue(
            maxsize=200
        )
        self._speaker_queue = queue.Queue(
            maxsize=400
        )

        self._input_stream = None
        self._output_stream = None
        self._speaker_thread = None

        self._android_sdl = None
        self._android_audio_record = None
        self._android_mic_thread = None
        self._android_mic_device = 0
        self._android_speaker_device = 0
        self._android_audio_lock = threading.Lock()

        self._last_error = ""
        self._running = False
        self._response_transcript = ""
        self._user_transcript = ""

        # One-response-per-turn protection. Realtime may occasionally
        # deliver a completed transcription event more than once.
        self._response_in_progress = False
        self._processed_transcript_ids = set()
        self._last_transcript_text = ""
        self._last_transcript_time = 0.0

        # Realtime function-tool state.
        self._pending_tool_followup = False

        self.reconnect_delay = 2.0
        self.max_reconnect_delay = 30.0

        # Reconnect diagnostics are intentionally throttled. A temporary
        # Wi-Fi/DNS outage can otherwise produce many identical UI errors
        # while the background reconnect loop is doing exactly what it should.
        self._last_connection_error_text = ""
        self._last_connection_error_time = 0.0
        self._connection_error_report_interval = 30.0

    @staticmethod
    def load_settings():
        defaults = {
            "provider": "OpenAI",
            "realtime_model": DEFAULT_MODEL,
            "realtime_voice": DEFAULT_VOICE,
            "voice_language": "en",
            "speaker_echo_protection": True,
            "realtime_instructions": (
                "You are Ace, the M12 AI assistant. "
                "Answer only the exact question asked. "
                "Give a short, direct answer unless the user "
                "explicitly requests more detail."
            ),
        }

        if not SETTINGS_FILE.exists():
            return defaults

        try:
            with SETTINGS_FILE.open(
                "r",
                encoding="utf-8",
            ) as file:
                loaded = json.load(file)

            if isinstance(
                loaded,
                dict,
            ):
                defaults.update(loaded)

        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            print(
                "Realtime settings error: "
                f"{type(error).__name__}: {error}"
            )

        return defaults

    @staticmethod
    def normalize_language(
        language,
    ):
        value = str(
            language
        ).strip().lower()

        aliases = {
            "english": "en",
            "en-us": "en",
            "en_us": "en",
            "russian": "ru",
            "ru-ru": "ru",
            "ru_ru": "ru",
            "automatic": "auto",
            "detect": "auto",
        }

        value = aliases.get(
            value,
            value,
        )

        if value not in {
            "en",
            "ru",
            "auto",
        }:
            return "auto"

        return value

    @property
    def is_running(self):
        return self._running

    @property
    def is_connected(self):
        return self._connected_event.is_set()

    @property
    def is_conversation_active(self):
        return self._conversation_active.is_set()

    @property
    def is_assistant_speaking(self):
        return self._assistant_speaking.is_set()

    @property
    def last_error(self):
        return self._last_error

    def set_language(
        self,
        language,
    ):
        """
        Set transcription language for the next connection.

        The session is restarted when it is already connected because
        Realtime session audio transcription settings are session-level.
        """
        normalized = self.normalize_language(
            language
        )

        changed = normalized != self.language
        self.language = normalized

        if changed and self.is_running:
            self.restart()

        return normalized

    def _refresh_echo_protection_setting(self):
        """Reload Speaker Echo Protection so Settings changes apply live."""
        try:
            settings = self.load_settings()
            self.speaker_echo_protection = bool(
                settings.get(
                    "speaker_echo_protection",
                    True,
                )
            )
        except Exception:
            pass

        return bool(
            self.speaker_echo_protection
        )

    def _pause_microphone_for_assistant(self):
        """Mute microphone capture; keep Realtime and speaker active."""
        if not self._refresh_echo_protection_setting():
            return False

        with self._echo_resume_lock:
            self._echo_resume_generation += 1

        if self._echo_paused_microphone:
            return True

        self._echo_paused_microphone = True
        self._assistant_speaking.set()

        # Android: keep the SDL capture device open for the whole voice
        # session. Repeated close/reopen cycles around every assistant
        # answer can race with the audio thread and destabilize the app.
        # Muting is therefore implemented by gating captured samples.
        if IS_ANDROID:
            self._microphone_enabled.clear()
        else:
            self._stop_microphone()

        self._drain_queue(
            self._microphone_queue
        )
        self._user_transcript = ""

        self._emit_status(
            "Ace speaking — microphone paused."
        )
        return True

    def _schedule_microphone_resume_after_speaker(self):
        """Resume microphone only after queued PCM has actually finished."""
        if not self._echo_paused_microphone:
            self._assistant_speaking.clear()
            return

        with self._echo_resume_lock:
            self._echo_resume_generation += 1
            generation = self._echo_resume_generation

        threading.Thread(
            target=self._resume_microphone_after_speaker_worker,
            args=(generation,),
            name="M12EchoProtectionResume",
            daemon=True,
        ).start()

    def _resume_microphone_after_speaker_worker(
        self,
        generation,
    ):
        quiet_started = None
        deadline = time.monotonic() + 30.0

        while (
            time.monotonic() < deadline
            and not self._stop_event.is_set()
        ):
            with self._echo_resume_lock:
                if generation != self._echo_resume_generation:
                    return

            with self._speaker_timing_lock:
                playback_until = self._speaker_playback_until

            playback_time_complete = (
                time.monotonic() >= playback_until
            )
            python_queue_empty = self._speaker_queue.empty()
            device_empty = True

            if IS_ANDROID:
                with self._android_audio_lock:
                    device_id = self._android_speaker_device

                if (
                    device_id
                    and self._android_sdl is not None
                ):
                    try:
                        device_empty = (
                            int(
                                self._android_sdl.SDL_GetQueuedAudioSize(
                                    device_id
                                )
                            )
                            == 0
                        )
                    except Exception:
                        device_empty = False

            if (
                playback_time_complete
                and python_queue_empty
                and device_empty
            ):
                if quiet_started is None:
                    quiet_started = time.monotonic()
                elif (
                    time.monotonic() - quiet_started
                    >= 0.55
                ):
                    break
            else:
                quiet_started = None

            time.sleep(0.03)

        with self._echo_resume_lock:
            if generation != self._echo_resume_generation:
                return

        self._echo_paused_microphone = False
        self._assistant_speaking.clear()

        if (
            self.is_connected
            and self.is_conversation_active
            and not self._stop_event.is_set()
        ):
            try:
                self._start_microphone()
                self._emit_status(
                    "Realtime voice is listening."
                )
            except Exception as error:
                self._report_error(
                    "Realtime microphone resume failed",
                    error,
                )

    def start(
        self,
        wait_until_ready=False,
        timeout=20.0,
    ):
        """
        Start the background Realtime connection.
        """
        if (
            self._thread is not None
            and self._thread.is_alive()
        ):
            if wait_until_ready:
                return self.wait_until_ready(
                    timeout=timeout
                )

            return True

        self._stop_event.clear()
        self._connected_event.clear()
        self._ready_event.clear()
        self._last_error = ""

        self._thread = threading.Thread(
            target=self._thread_main,
            name="M12RealtimeVoice",
            daemon=True,
        )

        self._thread.start()

        if wait_until_ready:
            return self.wait_until_ready(
                timeout=timeout
            )

        return True

    def wait_until_ready(
        self,
        timeout=20.0,
    ):
        ready = self._ready_event.wait(
            timeout=max(
                0.1,
                float(timeout),
            )
        )

        return bool(
            ready
            and self.is_connected
        )

    def start_conversation(
        self,
        timeout=20.0,
    ):
        """
        Connect and begin microphone streaming.

        Server VAD detects when the user starts and stops speaking.
        """
        if not self.start(
            wait_until_ready=True,
            timeout=timeout,
        ):
            raise RuntimeError(
                "Realtime connection is not ready. "
                f"{self._last_error}"
            )

        self._clear_audio_queues()

        # Mark the conversation active before starting audio threads.
        # The speaker worker checks this flag immediately; starting it
        # first caused the thread to exit before any audio arrived.
        self._conversation_active.set()
        self._microphone_enabled.set()

        try:
            self._start_speaker()
            self._start_microphone()

        except Exception:
            self._conversation_active.clear()
            self._stop_microphone()
            self._stop_speaker()
            raise

        self._emit_status(
            "Realtime voice is listening."
        )

        return True

    def pause_listening(
        self,
    ):
        """
        Temporarily pause microphone input while keeping Realtime connected.
        """
        self._conversation_active.clear()
        self._microphone_enabled.clear()
        self._stop_microphone()
        self._drain_queue(
            self._microphone_queue
        )
        self._user_transcript = ""

        self._emit_status(
            "Realtime paused."
        )

    def resume_listening(
        self,
    ):
        """
        Resume the original continuous speech-to-speech conversation.
        """
        if not self.is_connected:
            if not self.start(
                wait_until_ready=True,
                timeout=20.0,
            ):
                raise RuntimeError(
                    "Realtime connection is not ready. "
                    f"{self._last_error}"
                )

        self._drain_queue(
            self._microphone_queue
        )
        self._user_transcript = ""
        self._conversation_active.set()
        self._microphone_enabled.set()

        try:
            self._start_speaker()
            self._start_microphone()

        except Exception:
            self._conversation_active.clear()
            self._stop_microphone()
            self._stop_speaker()
            raise

        self._emit_status(
            "Realtime voice is listening."
        )

    def stop_conversation(
        self,
    ):
        """
        Stop microphone and speaker but keep WebSocket connected.
        """
        self._conversation_active.clear()
        self._microphone_enabled.clear()
        self._assistant_speaking.clear()
        self._echo_paused_microphone = False

        with self._echo_resume_lock:
            self._echo_resume_generation += 1

        self._stop_microphone()
        self._stop_speaker()
        self._clear_audio_queues()

        self._emit_status(
            "Realtime voice stopped."
        )

    def stop(
        self,
        timeout=6.0,
    ):
        """
        Stop microphone, speaker, connection, and event loop.
        """
        self.stop_conversation()
        self._stop_event.set()

        loop = self._loop

        if (
            loop is not None
            and loop.is_running()
        ):
            try:
                asyncio.run_coroutine_threadsafe(
                    self._request_shutdown(),
                    loop,
                )
            except Exception:
                pass

        thread = self._thread

        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(
                timeout=max(
                    0.1,
                    float(timeout),
                )
            )

        self._running = False
        self._connected_event.clear()
        self._ready_event.clear()

    def restart(
        self,
    ):
        active = self.is_conversation_active
        self.stop()
        time.sleep(0.2)
        self.start(
            wait_until_ready=True,
            timeout=20.0,
        )

        if active:
            self.start_conversation()

    def send_text(
        self,
        text,
        timeout=10.0,
    ):
        """
        Send a text message through the same Realtime session.
        """
        message = str(text).strip()

        if not message:
            return False

        if not self.is_running:
            self.start(
                wait_until_ready=True,
                timeout=timeout,
            )

        if not self.wait_until_ready(
            timeout=timeout
        ):
            raise RuntimeError(
                "Realtime connection is not ready. "
                f"{self._last_error}"
            )

        loop = self._loop

        if (
            loop is None
            or not loop.is_running()
            or self._send_queue is None
        ):
            raise RuntimeError(
                "Realtime event loop is not available."
            )

        future = asyncio.run_coroutine_threadsafe(
            self._send_queue.put(
                {
                    "type": "text",
                    "text": message,
                }
            ),
            loop,
        )

        future.result(
            timeout=max(
                1.0,
                float(timeout),
            )
        )

        return True

    def cancel_response(
        self,
    ):
        """
        Cancel current assistant response and clear queued audio.
        """
        self._assistant_speaking.clear()
        self._drain_queue(
            self._speaker_queue
        )

        loop = self._loop
        connection = self._connection

        if (
            loop is None
            or connection is None
            or not loop.is_running()
        ):
            return False

        try:
            future = (
                asyncio.run_coroutine_threadsafe(
                    connection.send(
                        {
                            "type": "response.cancel",
                        }
                    ),
                    loop,
                )
            )
            future.result(timeout=3.0)
            return True

        except Exception:
            return False

    def pause_microphone_for_local_answer(self):
        """Pause microphone capture while a local answer is spoken."""
        self._assistant_speaking.set()
        self._local_echo_suppress_until = float("inf")
        self._microphone_enabled.clear()

        # On Android do not close the SDL capture device for a temporary
        # local-speech pause. The worker remains alive and discards audio
        # until microphone capture is enabled again.
        if not IS_ANDROID:
            self._stop_microphone()

        self._drain_queue(
            self._microphone_queue
        )

    def resume_microphone_after_local_answer(self):
        """Resume microphone capture after a local answer finishes."""
        # Realtime transcription can arrive slightly after local TTS audio
        # physically ends. Ignore that delayed echo for a short grace period.
        self._local_echo_suppress_until = time.monotonic() + 1.5
        self._assistant_speaking.clear()

        if (
            self.is_connected
            and self.is_conversation_active
            and not self._stop_event.is_set()
        ):
            self._microphone_enabled.set()
            self._start_microphone()
            self._emit_status(
                "Realtime voice is listening."
            )

    def _thread_main(
        self,
    ):
        self._running = True

        try:
            asyncio.run(
                self._run()
            )

        except Exception as error:
            self._report_error(
                "Realtime thread failed",
                error,
            )

        finally:
            self._running = False
            self._connected_event.clear()
            self._ready_event.clear()
            self._connection = None
            self._loop = None

    async def _run(
        self,
    ):
        self._loop = asyncio.get_running_loop()
        self._send_queue = asyncio.Queue()

        delay = self.reconnect_delay

        while not self._stop_event.is_set():
            try:
                await self._connect_and_run()
                delay = self.reconnect_delay

            except asyncio.CancelledError:
                break

            except Exception as error:
                self._connected_event.clear()
                self._ready_event.clear()
                self._connection = None

                # A failed socket can leave turn/audio state marked active.
                # Reset only transient Realtime state; keep the user's
                # conversation/listening preference so reconnect can resume.
                self._response_in_progress = False
                self._pending_tool_followup = False
                self._assistant_speaking.clear()
                self._echo_paused_microphone = False
                self._microphone_enabled.clear()
                self._clear_audio_queues()

                error_text = (
                    f"{type(error).__name__}: {error}"
                ).strip()
                now = time.monotonic()

                should_report = (
                    error_text != self._last_connection_error_text
                    or (
                        now - self._last_connection_error_time
                        >= self._connection_error_report_interval
                    )
                )

                if should_report:
                    self._last_connection_error_text = error_text
                    self._last_connection_error_time = now
                    self._report_error(
                        "Realtime connection error",
                        error,
                    )
                else:
                    print(
                        "[Realtime] Repeated connection error suppressed: "
                        + error_text
                    )

                if self._stop_event.is_set():
                    break

                self._emit_status(
                    (
                        "Realtime disconnected. "
                        f"Reconnecting in {delay:.1f} seconds..."
                    )
                )

                # Sleep in short intervals so Stop/Restart does not have to
                # wait for the full reconnect backoff.
                wait_until = time.monotonic() + delay
                while (
                    not self._stop_event.is_set()
                    and time.monotonic() < wait_until
                ):
                    await asyncio.sleep(0.2)

                if self._stop_event.is_set():
                    break

                delay = min(
                    delay * 2.0,
                    self.max_reconnect_delay,
                )

    async def _connect_and_run(
        self,
    ):
        self._emit_status(
            "Connecting to OpenAI Realtime..."
        )

        ssl_context = ssl.create_default_context(
            cafile=certifi.where()
        )

        async with self.client.realtime.connect(
            model=self.model,
            websocket_connection_options={
                "ssl": ssl_context,
            },
        ) as connection:
            self._connection = connection

            await connection.session.update(
                session=self._session_configuration()
            )

            self._connected_event.set()
            self._ready_event.set()
            self._last_error = ""
            self._last_connection_error_text = ""
            self._last_connection_error_time = 0.0

            # If voice conversation was active before a network interruption,
            # resume microphone streaming automatically on the new socket.
            if self._conversation_active.is_set():
                self._microphone_enabled.set()
                self._drain_queue(self._microphone_queue)

            self._emit_status(
                "Realtime connected."
            )

            if self._conversation_active.is_set():
                self._emit_status(
                    "Realtime voice is listening."
                )

            receiver_task = asyncio.create_task(
                self._receive_events(
                    connection
                )
            )

            sender_task = asyncio.create_task(
                self._send_events(
                    connection
                )
            )

            microphone_task = asyncio.create_task(
                self._send_microphone_audio(
                    connection
                )
            )

            stop_task = asyncio.create_task(
                self._wait_for_stop()
            )

            done, pending = await asyncio.wait(
                {
                    receiver_task,
                    sender_task,
                    microphone_task,
                    stop_task,
                },
                return_when=(
                    asyncio.FIRST_COMPLETED
                ),
            )

            for task in pending:
                task.cancel()

            await asyncio.gather(
                *pending,
                return_exceptions=True,
            )

            for task in done:
                exception = task.exception()

                if exception is not None:
                    raise exception

    def _current_instructions(
        self,
    ):
        """
        Build Realtime instructions with the latest permanent memory.
        """
        try:
            self.permanent_memory.load()

            memory_context = (
                self.permanent_memory.get_prompt_context(
                    limit=50
                )
            )
        except Exception as error:
            print(
                "Realtime permanent-memory error: "
                f"{type(error).__name__}: {error}"
            )
            memory_context = ""

        instructions = self.instructions

        # The language selected on the AI screen controls BOTH
        # transcription and the assistant's spoken Realtime answer.
        if self.language == "en":
            instructions += (
                "\n\nLANGUAGE RULE: "
                "Always answer in English only, even when the user speaks "
                "Russian or another language. Understand the user's question, "
                "but translate your answer into natural American English. "
                "Do not answer in Russian unless the selected voice language "
                "is changed to Russian."
            )
        elif self.language == "ru":
            instructions += (
                "\n\nLANGUAGE RULE: "
                "Always answer in Russian only, even when the user speaks "
                "English or another language. Understand the user's question, "
                "but answer in natural Russian."
            )
        else:
            instructions += (
                "\n\nLANGUAGE RULE: "
                "Automatic language mode is selected. Answer in the same "
                "language used by the user for the current request."
            )

        if memory_context:
            instructions += (
                "\n\n"
                + memory_context
                + "\n\nUse these facts when relevant. "
                "Do not say that you are reading memory."
            )

        return instructions

    def _session_configuration(
        self,
    ):
        input_configuration = {
            "format": {
                "type": "audio/pcm",
                "rate": SAMPLE_RATE,
            },
            "noise_reduction": {
                "type": "near_field",
            },
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 650,
                "create_response": False,
                "interrupt_response": True,
            },
        }

        if self.language != "auto":
            input_configuration[
                "transcription"
            ] = {
                "model": (
                    "gpt-4o-mini-transcribe"
                ),
                "language": self.language,
                "prompt": (
                    "Transcribe accurately in "
                    + self.LANGUAGE_NAMES.get(
                        self.language,
                        self.language,
                    )
                    + "."
                ),
            }
        else:
            input_configuration[
                "transcription"
            ] = {
                "model": (
                    "gpt-4o-mini-transcribe"
                ),
            }

        return {
            "type": "realtime",
            "model": self.model,
            "output_modalities": [
                "audio",
            ],
            "instructions": self._current_instructions(),
            "tools": [
                {
                    "type": "function",
                    "name": "show_images",
                    "description": (
                        "Display pictures in the M12 AI screen. Use this tool "
                        "when the user wants to see pictures, images, photos, "
                        "portraits, or other visual examples. Resolve pronouns "
                        "and references from the conversation in any language "
                        "before calling the tool. Pass clean subject names only."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "subjects": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1,
                                "maxItems": 8,
                                "description": (
                                    "Exact subjects whose pictures should be "
                                    "displayed, one subject per array item."
                                ),
                            },
                        },
                        "required": ["subjects"],
                        "additionalProperties": False,
                    },
                },
            ],
            "tool_choice": "auto",
            "audio": {
                "input": input_configuration,
                "output": {
                    "format": {
                        "type": "audio/pcm",
                        "rate": SAMPLE_RATE,
                    },
                    "voice": self.voice,
                    "speed": 1.0,
                },
            },
        }

    async def _send_events(
        self,
        connection,
    ):
        while not self._stop_event.is_set():
            request = await self._send_queue.get()

            if request is None:
                break

            if request.get("type") == "text":
                await self._send_text_request(
                    connection=connection,
                    text=request.get(
                        "text",
                        "",
                    ),
                )

    async def _send_text_request(
        self,
        connection,
        text,
    ):
        message = str(text).strip()

        if not message:
            return

        self._emit_status(
            "Realtime answering..."
        )

        await connection.conversation.item.create(
            item={
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": message,
                    }
                ],
            }
        )

        await self._create_response_once(
            connection
        )

    async def _create_response_once(
        self,
        connection,
    ):
        """Start at most one assistant response for the current turn."""
        if self._response_in_progress:
            print(
                "[Realtime] Response already in progress; "
                "duplicate response request ignored."
            )
            return False

        self._response_in_progress = True

        try:
            await connection.response.create()
            return True
        except Exception:
            self._response_in_progress = False
            raise

    def _is_duplicate_transcript(
        self,
        event,
        transcript,
    ):
        """Return True when a completed transcript event was already handled."""
        item_id = str(
            getattr(
                event,
                "item_id",
                "",
            )
        ).strip()

        if item_id:
            if item_id in self._processed_transcript_ids:
                return True

            self._processed_transcript_ids.add(item_id)

            # Prevent an unbounded set during very long sessions.
            if len(self._processed_transcript_ids) > 500:
                self._processed_transcript_ids.clear()
                self._processed_transcript_ids.add(item_id)

            return False

        normalized = " ".join(
            str(transcript).strip().lower().split()
        )
        now = time.monotonic()

        duplicate = (
            normalized
            and normalized == self._last_transcript_text
            and now - self._last_transcript_time < 2.0
        )

        self._last_transcript_text = normalized
        self._last_transcript_time = now
        return duplicate

    async def _send_microphone_audio(
        self,
        connection,
    ):
        """
        Transfer microphone callback data to the WebSocket.
        """
        while not self._stop_event.is_set():
            if (
                not self._conversation_active.is_set()
                or not self._microphone_enabled.is_set()
            ):
                await asyncio.sleep(0.02)
                continue

            try:
                audio_bytes = (
                    self._microphone_queue.get_nowait()
                )
            except queue.Empty:
                await asyncio.sleep(0.005)
                continue

            encoded = base64.b64encode(
                audio_bytes
            ).decode("ascii")

            await connection.input_audio_buffer.append(
                audio=encoded
            )

    async def _receive_events(
        self,
        connection,
    ):
        async for event in connection:
            if self._stop_event.is_set():
                break

            event_type = str(
                getattr(
                    event,
                    "type",
                    "",
                )
            )

            if event_type == (
                "input_audio_buffer.speech_started"
            ):
                # A new user turn interrupts the previous response.
                self._response_in_progress = False
                self._response_transcript = ""
                self._emit_speech_started()

            elif event_type == (
                "input_audio_buffer.speech_stopped"
            ):
                self._emit_speech_stopped()

            elif event_type == (
                "conversation.item.input_audio_transcription.delta"
            ):
                delta = str(
                    getattr(
                        event,
                        "delta",
                        "",
                    )
                )

                if delta:
                    self._user_transcript += delta

            elif event_type == (
                "conversation.item.input_audio_transcription.completed"
            ):
                transcript = str(
                    getattr(
                        event,
                        "transcript",
                        self._user_transcript,
                    )
                ).strip()

                if not transcript:
                    transcript = (
                        self._user_transcript.strip()
                    )

                self._user_transcript = ""

                if transcript:
                    if (
                        self._assistant_speaking.is_set()
                        or time.monotonic() < self._local_echo_suppress_until
                    ):
                        print(
                            "[Realtime] Ignored local-speaker echo transcript: "
                            + transcript
                        )
                        continue

                    if self._is_duplicate_transcript(
                        event,
                        transcript,
                    ):
                        print(
                            "[Realtime] Duplicate completed "
                            "transcript ignored."
                        )
                        continue

                    self._emit_user_transcript(
                        transcript
                    )

                    handled, answer = (
                        self._route_local_request(
                            transcript
                        )
                    )

                    # Image display is an AI capability. If the legacy local
                    # router recognizes an image request, do not execute that
                    # result here; let Realtime resolve context and call the
                    # structured show_images tool instead.
                    if (
                        handled
                        and str(answer).strip().startswith(
                            "__M12_IMAGE_SUBJECTS__:"
                        )
                    ):
                        handled = False

                    if handled:
                        self._emit_local_answer(
                            answer
                        )
                    else:
                        self._emit_status(
                            "Realtime answering..."
                        )
                        await self._create_response_once(
                            connection
                        )

            elif event_type == (
                "response.function_call_arguments.done"
            ):
                await self._handle_function_call(
                    connection=connection,
                    event=event,
                )

            elif event_type == (
                "response.output_audio.delta"
            ):
                delta = str(
                    getattr(
                        event,
                        "delta",
                        "",
                    )
                )

                if delta:
                    audio_bytes = (
                        base64.b64decode(
                            delta
                        )
                    )

                    if (
                        self._refresh_echo_protection_setting()
                        and not self._echo_paused_microphone
                    ):
                        self._pause_microphone_for_assistant()
                    else:
                        self._assistant_speaking.set()

                    self._queue_speaker_audio(
                        audio_bytes
                    )

            elif event_type == (
                "response.output_audio.done"
            ):
                if self._echo_paused_microphone:
                    self._schedule_microphone_resume_after_speaker()
                else:
                    self._assistant_speaking.clear()

            elif event_type == (
                "response.output_audio_transcript.delta"
            ):
                delta = str(
                    getattr(
                        event,
                        "delta",
                        "",
                    )
                )

                if delta:
                    self._response_transcript += delta
                    self._emit_text_delta(
                        delta
                    )

            elif event_type == (
                "response.output_audio_transcript.done"
            ):
                transcript = str(
                    getattr(
                        event,
                        "transcript",
                        self._response_transcript,
                    )
                ).strip()

                if not transcript:
                    transcript = (
                        self._response_transcript.strip()
                    )

                self._response_transcript = ""

                if transcript:
                    self._emit_text_done(
                        transcript
                    )

            elif event_type == (
                "response.done"
            ):
                self._response_in_progress = False

                if self._echo_paused_microphone:
                    self._schedule_microphone_resume_after_speaker()
                else:
                    self._assistant_speaking.clear()

                if self._pending_tool_followup:
                    self._pending_tool_followup = False
                    self._emit_status(
                        "Realtime answering..."
                    )
                    await self._create_response_once(
                        connection
                    )
                else:
                    self._emit_status(
                        "Realtime ready."
                    )

            elif event_type == "error":
                self._response_in_progress = False
                error_object = getattr(
                    event,
                    "error",
                    None,
                )

                message = str(
                    getattr(
                        error_object,
                        "message",
                        "Unknown Realtime error",
                    )
                )

                code = str(
                    getattr(
                        error_object,
                        "code",
                        "",
                    )
                )

                if code:
                    message = (
                        f"{code}: {message}"
                    )

                self._last_error = message
                self._emit_error(
                    message
                )

    async def _handle_function_call(
        self,
        connection,
        event,
    ):
        """Execute a Realtime function call and return its result."""
        name = str(getattr(event, "name", "")).strip()
        call_id = str(getattr(event, "call_id", "")).strip()
        raw_arguments = getattr(event, "arguments", "{}")

        if not call_id:
            print(
                "[Realtime] Function call ignored because call_id is missing."
            )
            return

        if name == "show_images":
            output = self._execute_show_images_tool(
                raw_arguments
            )
        else:
            output = {
                "ok": False,
                "error": "Unsupported M12 tool.",
            }

        await connection.conversation.item.create(
            item={
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(
                    output,
                    ensure_ascii=False,
                ),
            }
        )

        self._pending_tool_followup = True

    def _execute_show_images_tool(
        self,
        raw_arguments,
    ):
        """Execute the model-selected image request through M12 ImageSkill."""
        try:
            if isinstance(raw_arguments, str):
                arguments = json.loads(raw_arguments or "{}")
            elif isinstance(raw_arguments, dict):
                arguments = raw_arguments
            else:
                arguments = {}
        except json.JSONDecodeError as error:
            print(
                "[Realtime] show_images arguments error: "
                f"{type(error).__name__}: {error}"
            )
            return {
                "ok": False,
                "error": "Invalid show_images arguments.",
            }

        raw_subjects = arguments.get("subjects", [])
        if isinstance(raw_subjects, str):
            raw_subjects = [raw_subjects]

        subjects = []
        if isinstance(raw_subjects, (list, tuple)):
            for subject in raw_subjects:
                clean = " ".join(str(subject).strip().split())
                if clean and clean not in subjects:
                    subjects.append(clean)
                if len(subjects) >= 8:
                    break

        if not subjects:
            return {
                "ok": False,
                "error": "No image subjects were supplied.",
            }

        command = (
            "__M12_IMAGE_SUBJECTS__:"
            + json.dumps(subjects, ensure_ascii=False)
        )

        print(
            "[Realtime] show_images subjects: "
            + repr(subjects)
        )

        handled, answer = self._route_local_request(
            command
        )

        if not handled:
            return {
                "ok": False,
                "error": "M12 image display did not accept the request.",
                "subjects": subjects,
            }

        if answer:
            self._emit_local_answer(answer)

        return {
            "ok": True,
            "subjects": subjects,
        }

    # -------------------------------------------------------------
    # Android SDL2 audio backend
    # -------------------------------------------------------------
    def _load_android_sdl(
        self,
    ):
        if not IS_ANDROID:
            raise RuntimeError(
                "Android SDL2 audio requested on a non-Android platform."
            )

        if self._android_sdl is not None:
            return self._android_sdl

        candidates = []

        found = ctypes.util.find_library("SDL2")
        if found:
            candidates.append(found)

        candidates.extend(
            [
                "libSDL2.so",
                "SDL2",
            ]
        )

        last_error = None
        sdl = None

        for name in candidates:
            try:
                sdl = ctypes.CDLL(name)
                break
            except Exception as error:
                last_error = error

        if sdl is None:
            raise RuntimeError(
                "SDL2 audio library could not be loaded on Android. "
                f"Last error: {last_error}"
            )

        sdl.SDL_InitSubSystem.argtypes = [ctypes.c_uint32]
        sdl.SDL_InitSubSystem.restype = ctypes.c_int

        sdl.SDL_GetError.argtypes = []
        sdl.SDL_GetError.restype = ctypes.c_char_p

        sdl.SDL_OpenAudioDevice.argtypes = [
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.POINTER(SDL_AudioSpec),
            ctypes.POINTER(SDL_AudioSpec),
            ctypes.c_int,
        ]
        sdl.SDL_OpenAudioDevice.restype = ctypes.c_uint32

        sdl.SDL_PauseAudioDevice.argtypes = [
            ctypes.c_uint32,
            ctypes.c_int,
        ]
        sdl.SDL_PauseAudioDevice.restype = None

        sdl.SDL_CloseAudioDevice.argtypes = [ctypes.c_uint32]
        sdl.SDL_CloseAudioDevice.restype = None

        sdl.SDL_ClearQueuedAudio.argtypes = [ctypes.c_uint32]
        sdl.SDL_ClearQueuedAudio.restype = None

        sdl.SDL_GetQueuedAudioSize.argtypes = [ctypes.c_uint32]
        sdl.SDL_GetQueuedAudioSize.restype = ctypes.c_uint32

        sdl.SDL_DequeueAudio.argtypes = [
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        sdl.SDL_DequeueAudio.restype = ctypes.c_uint32

        sdl.SDL_QueueAudio.argtypes = [
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        sdl.SDL_QueueAudio.restype = ctypes.c_int

        result = sdl.SDL_InitSubSystem(SDL_INIT_AUDIO)

        if result != 0:
            raise RuntimeError(
                "SDL2 Android audio initialization failed: "
                + self._android_sdl_error(sdl)
            )

        self._android_sdl = sdl
        return sdl

    @staticmethod
    def _android_sdl_error(
        sdl,
    ):
        try:
            value = sdl.SDL_GetError()
            if value:
                return value.decode(
                    "utf-8",
                    errors="replace",
                )
        except Exception:
            pass

        return "Unknown SDL2 audio error"

    def _check_android_microphone_permission(
        self,
    ):
        try:
            from android.permissions import (
                Permission,
                check_permission,
            )

            if check_permission(Permission.RECORD_AUDIO):
                return True

        except Exception as error:
            raise RuntimeError(
                "Unable to check Android microphone permission: "
                f"{type(error).__name__}: {error}"
            ) from error

        raise RuntimeError(
            "Android microphone permission is not granted. "
            "Allow Microphone permission for M12 OS."
        )

    def _open_android_audio_device(
        self,
        *,
        capture,
    ):
        sdl = self._load_android_sdl()

        desired = SDL_AudioSpec()
        desired.freq = SAMPLE_RATE
        desired.format = AUDIO_S16LSB
        desired.channels = CHANNELS
        desired.samples = INPUT_FRAMES
        desired.callback = None
        desired.userdata = None

        obtained = SDL_AudioSpec()

        device_id = sdl.SDL_OpenAudioDevice(
            None,
            1 if capture else 0,
            ctypes.byref(desired),
            ctypes.byref(obtained),
            0,
        )

        if device_id == 0:
            kind = "microphone" if capture else "speaker"
            raise RuntimeError(
                f"Unable to open Android {kind} at "
                f"{SAMPLE_RATE} Hz: "
                + self._android_sdl_error(sdl)
            )

        if (
            int(obtained.format) != AUDIO_S16LSB
            or int(obtained.channels) != CHANNELS
            or int(obtained.freq) != SAMPLE_RATE
        ):
            try:
                sdl.SDL_CloseAudioDevice(device_id)
            except Exception:
                pass

            raise RuntimeError(
                "Android audio device did not accept "
                "24 kHz mono signed 16-bit PCM. "
                f"Obtained: {int(obtained.freq)} Hz, "
                f"{int(obtained.channels)} channel(s), "
                f"format=0x{int(obtained.format):04x}"
            )

        return sdl, int(device_id)

    def _android_microphone_worker(
        self,
    ):
        """
        Android microphone capture using the platform AudioRecord API.

        Important:
            The speaker still uses SDL2 on Android. Only microphone capture
            is moved away from direct SDL2/ctypes calls because repeated
            native capture-device access has produced intermittent SIGSEGV
            crashes on Android.
        """
        recorder = None
        recording_started = False

        try:
            self._check_android_microphone_permission()

            from jnius import autoclass

            AudioRecord = autoclass(
                "android.media.AudioRecord"
            )
            AudioFormat = autoclass(
                "android.media.AudioFormat"
            )
            AudioSource = autoclass(
                "android.media.MediaRecorder$AudioSource"
            )

            channel_config = int(
                AudioFormat.CHANNEL_IN_MONO
            )
            audio_format = int(
                AudioFormat.ENCODING_PCM_16BIT
            )

            # Prefer the native 24 kHz rate expected by OpenAI Realtime.
            # Most modern Android devices support it. If the device reports
            # that 24 kHz is unavailable, fall back to 48 kHz and downsample
            # by 2 before placing PCM into the Realtime queue.
            capture_rate = SAMPLE_RATE
            min_buffer = int(
                AudioRecord.getMinBufferSize(
                    capture_rate,
                    channel_config,
                    audio_format,
                )
            )

            if min_buffer <= 0:
                capture_rate = SAMPLE_RATE * 2
                min_buffer = int(
                    AudioRecord.getMinBufferSize(
                        capture_rate,
                        channel_config,
                        audio_format,
                    )
                )

            if min_buffer <= 0:
                raise RuntimeError(
                    "Android AudioRecord does not support "
                    "24 kHz or 48 kHz mono PCM16 input."
                )

            output_frames = INPUT_FRAMES
            capture_frames = (
                output_frames
                if capture_rate == SAMPLE_RATE
                else output_frames * 2
            )

            read_bytes = (
                capture_frames
                * CHANNELS
                * SAMPLE_WIDTH
            )

            recorder_buffer_bytes = max(
                min_buffer * 2,
                read_bytes * 4,
            )

            source_candidates = [
                int(AudioSource.VOICE_RECOGNITION),
                int(AudioSource.MIC),
            ]

            last_error = None

            for source in source_candidates:
                candidate = None

                try:
                    candidate = AudioRecord(
                        source,
                        capture_rate,
                        channel_config,
                        audio_format,
                        recorder_buffer_bytes,
                    )

                    if int(candidate.getState()) != int(
                        AudioRecord.STATE_INITIALIZED
                    ):
                        try:
                            candidate.release()
                        except Exception:
                            pass
                        candidate = None
                        continue

                    recorder = candidate
                    break

                except Exception as error:
                    last_error = error

                    if candidate is not None:
                        try:
                            candidate.release()
                        except Exception:
                            pass

            if recorder is None:
                raise RuntimeError(
                    "Unable to initialize Android AudioRecord"
                    + (
                        f": {type(last_error).__name__}: {last_error}"
                        if last_error is not None
                        else "."
                    )
                )

            # Store only for diagnostics. The worker owns start/stop/release.
            self._android_audio_record = recorder

            recorder.startRecording()
            recording_started = True

            if int(recorder.getRecordingState()) != int(
                AudioRecord.RECORDSTATE_RECORDING
            ):
                raise RuntimeError(
                    "Android AudioRecord did not enter recording state."
                )

            audio_buffer = bytearray(
                read_bytes
            )

            while (
                not self._stop_event.is_set()
                and self._conversation_active.is_set()
            ):
                received = int(
                    recorder.read(
                        audio_buffer,
                        0,
                        read_bytes,
                    )
                )

                if received <= 0:
                    if received == int(
                        AudioRecord.ERROR_DEAD_OBJECT
                    ):
                        raise RuntimeError(
                            "Android AudioRecord device became unavailable."
                        )

                    if received in {
                        int(AudioRecord.ERROR_BAD_VALUE),
                        int(AudioRecord.ERROR_INVALID_OPERATION),
                        int(AudioRecord.ERROR),
                    }:
                        raise RuntimeError(
                            "Android AudioRecord read failed "
                            f"with code {received}."
                        )

                    time.sleep(0.005)
                    continue

                # PCM16 frames must end on a complete sample boundary.
                received -= received % SAMPLE_WIDTH

                if received <= 0:
                    continue

                audio_bytes = bytes(
                    audio_buffer[:received]
                )

                # If 24 kHz capture was unavailable, AudioRecord is running
                # at 48 kHz. Downsample mono PCM16 by keeping every second
                # sample, producing the 24 kHz PCM required by Realtime.
                if capture_rate != SAMPLE_RATE:
                    samples = memoryview(
                        audio_bytes
                    ).cast("h")

                    downsampled = bytearray(
                        (len(samples) // 2)
                        * SAMPLE_WIDTH
                    )
                    out_samples = memoryview(
                        downsampled
                    ).cast("h")

                    output_count = min(
                        len(out_samples),
                        len(samples) // 2,
                    )

                    for index in range(output_count):
                        out_samples[index] = samples[
                            index * 2
                        ]

                    audio_bytes = bytes(
                        downsampled[
                            :output_count * SAMPLE_WIDTH
                        ]
                    )

                # Speaker/local-TTS echo protection: continue reading from
                # AudioRecord so Android's input buffer stays healthy, but
                # discard captured samples while microphone input is muted.
                if not self._microphone_enabled.is_set():
                    continue

                try:
                    self._microphone_queue.put_nowait(
                        audio_bytes
                    )

                except queue.Full:
                    try:
                        self._microphone_queue.get_nowait()
                    except queue.Empty:
                        pass

                    try:
                        self._microphone_queue.put_nowait(
                            audio_bytes
                        )
                    except queue.Full:
                        pass

        except Exception as error:
            if (
                self._conversation_active.is_set()
                and not self._stop_event.is_set()
            ):
                self._report_error(
                    "Realtime Android AudioRecord microphone failed",
                    error,
                )

        finally:
            if recorder is not None:
                if recording_started:
                    try:
                        recorder.stop()
                    except Exception:
                        pass

                try:
                    recorder.release()
                except Exception:
                    pass

            if getattr(
                self,
                "_android_audio_record",
                None,
            ) is recorder:
                self._android_audio_record = None


    def _android_speaker_worker(
        self,
    ):
        device_id = 0

        try:
            sdl, device_id = self._open_android_audio_device(
                capture=False
            )

            with self._android_audio_lock:
                self._android_speaker_device = device_id

            sdl.SDL_ClearQueuedAudio(device_id)
            sdl.SDL_PauseAudioDevice(device_id, 0)

            max_queued_bytes = (
                SAMPLE_RATE
                * CHANNELS
                * SAMPLE_WIDTH
                * 2
            )

            while (
                not self._stop_event.is_set()
                and self._conversation_active.is_set()
            ):
                try:
                    audio_bytes = self._speaker_queue.get(
                        timeout=0.2
                    )
                except queue.Empty:
                    continue

                if audio_bytes is None:
                    break

                if not audio_bytes:
                    continue

                while (
                    int(
                        sdl.SDL_GetQueuedAudioSize(
                            device_id
                        )
                    ) > max_queued_bytes
                    and not self._stop_event.is_set()
                    and self._conversation_active.is_set()
                ):
                    time.sleep(0.01)

                buffer = ctypes.create_string_buffer(
                    audio_bytes,
                    len(audio_bytes),
                )

                result = sdl.SDL_QueueAudio(
                    device_id,
                    buffer,
                    len(audio_bytes),
                )

                if result != 0:
                    raise RuntimeError(
                        "SDL2 speaker queue failed: "
                        + self._android_sdl_error(sdl)
                    )

        except Exception as error:
            if (
                self._conversation_active.is_set()
                and not self._stop_event.is_set()
            ):
                self._report_error(
                    "Realtime Android speaker failed",
                    error,
                )

        finally:
            if device_id and self._android_sdl is not None:
                try:
                    self._android_sdl.SDL_ClearQueuedAudio(
                        device_id
                    )
                except Exception:
                    pass

                try:
                    self._android_sdl.SDL_PauseAudioDevice(
                        device_id,
                        1,
                    )
                except Exception:
                    pass

                try:
                    self._android_sdl.SDL_CloseAudioDevice(
                        device_id
                    )
                except Exception:
                    pass

            with self._android_audio_lock:
                if self._android_speaker_device == device_id:
                    self._android_speaker_device = 0

    def _start_microphone(
        self,
    ):
        self._microphone_enabled.set()

        if IS_ANDROID:
            if (
                self._android_mic_thread is not None
                and self._android_mic_thread.is_alive()
            ):
                return

            self._check_android_microphone_permission()

            self._android_mic_thread = threading.Thread(
                target=self._android_microphone_worker,
                name="M12RealtimeAndroidMic",
                daemon=True,
            )
            self._android_mic_thread.start()
            return

        if not SOUNDDEVICE_AVAILABLE:
            raise RuntimeError(
                "Microphone audio is unavailable because "
                "sounddevice/PortAudio is not available. "
                + SOUNDDEVICE_ERROR
            )

        if self._input_stream is not None:
            return

        try:
            self._input_stream = (
                sd.RawInputStream(
                    samplerate=SAMPLE_RATE,
                    blocksize=INPUT_FRAMES,
                    channels=CHANNELS,
                    dtype="int16",
                    callback=(
                        self._microphone_callback
                    ),
                )
            )

            self._input_stream.start()

        except Exception as error:
            self._input_stream = None

            raise RuntimeError(
                "Unable to start microphone at "
                f"{SAMPLE_RATE} Hz: {error}"
            ) from error

    def _stop_microphone(
        self,
    ):
        self._microphone_enabled.clear()

        if IS_ANDROID:
            thread = self._android_mic_thread

            if (
                thread is not None
                and thread.is_alive()
                and thread is not threading.current_thread()
            ):
                thread.join(timeout=1.0)

            self._android_mic_thread = None
            return

        stream = self._input_stream
        self._input_stream = None

        if stream is None:
            return

        try:
            stream.stop()
        except Exception:
            pass

        try:
            stream.close()
        except Exception:
            pass

    def _microphone_callback(
        self,
        indata,
        frames,
        time_info,
        status,
    ):
        if status:
            print(
                f"Realtime microphone status: {status}"
            )

        if (
            not self._conversation_active.is_set()
            or not self._microphone_enabled.is_set()
        ):
            return

        audio_bytes = bytes(indata)

        try:
            self._microphone_queue.put_nowait(
                audio_bytes
            )

        except queue.Full:
            try:
                self._microphone_queue.get_nowait()
            except queue.Empty:
                pass

            try:
                self._microphone_queue.put_nowait(
                    audio_bytes
                )
            except queue.Full:
                pass

    def _start_speaker(
        self,
    ):
        if (
            self._speaker_thread is not None
            and self._speaker_thread.is_alive()
        ):
            return

        self._speaker_thread = threading.Thread(
            target=self._speaker_worker,
            name="M12RealtimeSpeaker",
            daemon=True,
        )

        self._speaker_thread.start()

    def _stop_speaker(
        self,
    ):
        try:
            self._speaker_queue.put_nowait(
                None
            )
        except queue.Full:
            self._drain_queue(
                self._speaker_queue
            )
            try:
                self._speaker_queue.put_nowait(
                    None
                )
            except queue.Full:
                pass

        thread = self._speaker_thread

        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=2.0)

        self._speaker_thread = None

    def _speaker_worker(
        self,
    ):
        if IS_ANDROID:
            self._android_speaker_worker()
            return

        if not SOUNDDEVICE_AVAILABLE:
            self._report_error(
                "Realtime speaker unavailable",
                RuntimeError(
                    "sounddevice/PortAudio is not available. "
                    + SOUNDDEVICE_ERROR
                ),
            )
            return

        try:
            self._output_stream = (
                sd.RawOutputStream(
                    samplerate=SAMPLE_RATE,
                    blocksize=0,
                    channels=CHANNELS,
                    dtype="int16",
                )
            )

            self._output_stream.start()

            while (
                not self._stop_event.is_set()
                and self._conversation_active.is_set()
            ):
                try:
                    audio_bytes = (
                        self._speaker_queue.get(
                            timeout=0.2
                        )
                    )
                except queue.Empty:
                    continue

                if audio_bytes is None:
                    break

                self._output_stream.write(
                    audio_bytes
                )

        except Exception as error:
            self._report_error(
                "Realtime speaker failed",
                error,
            )

        finally:
            stream = self._output_stream
            self._output_stream = None

            if stream is not None:
                try:
                    stream.stop()
                except Exception:
                    pass

                try:
                    stream.close()
                except Exception:
                    pass

    def _queue_speaker_audio(
        self,
        audio_bytes,
    ):
        try:
            byte_count = len(
                audio_bytes or b""
            )
        except Exception:
            byte_count = 0

        if byte_count > 0:
            bytes_per_second = (
                SAMPLE_RATE
                * CHANNELS
                * SAMPLE_WIDTH
            )
            duration = (
                float(byte_count)
                / float(bytes_per_second)
            )

            now = time.monotonic()

            with self._speaker_timing_lock:
                start_at = max(
                    now,
                    self._speaker_playback_until,
                )
                self._speaker_playback_until = (
                    start_at + duration
                )

        try:
            self._speaker_queue.put_nowait(
                audio_bytes
            )

        except queue.Full:
            try:
                self._speaker_queue.get_nowait()
            except queue.Empty:
                pass

            try:
                self._speaker_queue.put_nowait(
                    audio_bytes
                )
            except queue.Full:
                pass

    async def _wait_for_stop(
        self,
    ):
        while not self._stop_event.is_set():
            await asyncio.sleep(0.1)

    async def _request_shutdown(
        self,
    ):
        if self._send_queue is not None:
            await self._send_queue.put(None)

    def _clear_audio_queues(
        self,
    ):
        self._drain_queue(
            self._microphone_queue
        )
        self._drain_queue(
            self._speaker_queue
        )

        with self._speaker_timing_lock:
            self._speaker_playback_until = 0.0

    @staticmethod
    def _drain_queue(
        target_queue,
    ):
        while True:
            try:
                target_queue.get_nowait()
            except queue.Empty:
                break

    def _route_local_request(
        self,
        transcript,
    ):
        """Return (handled, answer) from the M12 local router callback."""
        if self.on_local_request is None:
            return False, ""

        try:
            result = self.on_local_request(
                str(transcript)
            )

            if (
                isinstance(result, tuple)
                and len(result) >= 2
            ):
                handled = bool(result[0])
                answer = str(result[1] or "").strip()
                return handled, answer

            return False, ""

        except Exception as error:
            print(
                "Realtime local-router callback error: "
                f"{type(error).__name__}: {error}"
            )
            return False, ""

    def _emit_local_answer(
        self,
        answer,
    ):
        text = str(answer or "").strip()

        if not text:
            return

        if self.on_local_answer is not None:
            try:
                self.on_local_answer(text)
                return
            except Exception as error:
                print(
                    "Realtime local-answer callback error: "
                    f"{type(error).__name__}: {error}"
                )

        print(
            f"\n[M12 LOCAL] {text}"
        )

    def _emit_status(
        self,
        message,
    ):
        text = str(message)

        if self.on_status is not None:
            try:
                self.on_status(text)
                return
            except Exception as error:
                print(
                    "Realtime status callback error: "
                    f"{error}"
                )

        print(
            f"[STATUS] {text}"
        )

    def _emit_user_transcript(
        self,
        transcript,
    ):
        if self.on_user_transcript is not None:
            try:
                self.on_user_transcript(
                    str(transcript)
                )
                return
            except Exception as error:
                print(
                    "Realtime transcript callback error: "
                    f"{error}"
                )

        print(
            f"\n[YOU] {transcript}"
        )

    def _emit_text_delta(
        self,
        delta,
    ):
        if self.on_text_delta is not None:
            try:
                self.on_text_delta(
                    str(delta)
                )
                return
            except Exception as error:
                print(
                    "Realtime delta callback error: "
                    f"{error}"
                )

        print(
            str(delta),
            end="",
            flush=True,
        )

    def _emit_text_done(
        self,
        text,
    ):
        if self.on_text_done is not None:
            try:
                self.on_text_done(
                    str(text)
                )
                return
            except Exception as error:
                print(
                    "Realtime done callback error: "
                    f"{error}"
                )

        print()

    def _emit_speech_started(
        self,
    ):
        # Clear audio that has not yet played when the user interrupts.
        self._assistant_speaking.clear()
        self._drain_queue(
            self._speaker_queue
        )

        if self.on_speech_started is not None:
            try:
                self.on_speech_started()
                return
            except Exception as error:
                print(
                    "Realtime speech-start callback error: "
                    f"{error}"
                )

        print(
            "\n[LISTENING] Speech started."
        )

    def _emit_speech_stopped(
        self,
    ):
        if self.on_speech_stopped is not None:
            try:
                self.on_speech_stopped()
                return
            except Exception as error:
                print(
                    "Realtime speech-stop callback error: "
                    f"{error}"
                )

        print(
            "[THINKING] Speech stopped."
        )

    def _emit_error(
        self,
        message,
    ):
        if self.on_error is not None:
            try:
                self.on_error(
                    str(message)
                )
                return
            except Exception as error:
                print(
                    "Realtime error callback error: "
                    f"{error}"
                )

        print(
            f"[ERROR] {message}"
        )

    def _report_error(
        self,
        prefix,
        error,
    ):
        message = (
            f"{prefix}: "
            f"{type(error).__name__}: {error}"
        )

        self._last_error = message
        self._emit_error(
            message
        )


def run_audio_test():
    """
    Standalone microphone and speaker test.

    Steps:
        1. Connect to Realtime.
        2. Start microphone and speaker.
        3. Speak one short question.
        4. Server VAD detects the end of speech.
        5. Ace answers through the speakers.
        6. Press Enter to stop the test.
    """
    print(
        "Starting M12 Realtime audio test..."
    )
    print(
        "Use headphones if possible to avoid speaker echo."
    )

    service = RealtimeVoiceService()

    try:
        connected = service.start(
            wait_until_ready=True,
            timeout=20.0,
        )

        if not connected:
            raise RuntimeError(
                "Realtime connection did not become ready. "
                f"{service.last_error}"
            )

        service.start_conversation()

        print()
        print(
            "Speak naturally. For example:"
        )
        print(
            '  "What is two plus two?"'
        )
        print()
        input(
            "Press Enter after you hear Ace answer..."
        )

    finally:
        service.stop()


if __name__ == "__main__":
    run_audio_test()