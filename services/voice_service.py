import json
import os
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_FILE = BASE_DIR / "config" / "ai_settings.json"


class VoiceService:
    """
    M12 voice service.

    Features:
        1. Record microphone audio
        2. Convert speech to text
        3. Convert AI text answers to speech
        4. Play and stop spoken answers
    """

    def __init__(self):
        settings = self.load_settings()

        saved_api_key = str(settings.get("api_key", "")).strip()
        environment_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        api_key = saved_api_key or environment_api_key

        if not api_key:
            raise RuntimeError("OpenAI API key is not configured.")

        self.client = OpenAI(api_key=api_key, timeout=90.0)

        self.transcription_model = str(
            settings.get("transcription_model", "gpt-4o-mini-transcribe")
        ).strip() or "gpt-4o-mini-transcribe"

        self.speech_model = str(
            settings.get("speech_model", "gpt-4o-mini-tts")
        ).strip() or "gpt-4o-mini-tts"

        self.speech_voice = str(
            settings.get("speech_voice", "marin")
        ).strip().lower() or "marin"

        self.speech_instructions = str(
            settings.get(
                "speech_instructions",
                "Speak clearly, naturally, and warmly. Use a calm personal-assistant style.",
            )
        ).strip()

        self.voice_answers_enabled = bool(
            settings.get("voice_answers_enabled", True)
        )

        self.transcription_language = self.normalize_language(
            settings.get(
                "voice_language",
                "en",
            )
        )

        self.sample_rate = 16000
        self.channels = 1
        self.record_seconds = 6

        self.playback_process = None
        self.playback_file = None
        self.playback_lock = threading.Lock()

    @staticmethod
    def load_settings():
        default_settings = {
            "provider": "OpenAI",
            "model": "gpt-5-mini",
            "transcription_model": "gpt-4o-mini-transcribe",
            "speech_model": "gpt-4o-mini-tts",
            "speech_voice": "marin",
            "speech_instructions": (
                "Speak clearly, naturally, and warmly. "
                "Use a calm personal-assistant style."
            ),
            "voice_answers_enabled": True,
            "voice_language": "en",
            "api_key": "",
        }

        if not SETTINGS_FILE.exists():
            return default_settings

        try:
            with SETTINGS_FILE.open("r", encoding="utf-8") as file:
                loaded = json.load(file)

            if isinstance(loaded, dict):
                default_settings.update(loaded)

        except (OSError, json.JSONDecodeError) as error:
            print(
                "Voice settings error: "
                f"{type(error).__name__}: {error}"
            )

        return default_settings

    @staticmethod
    def normalize_language(
        language,
    ):
        """
        Return a supported transcription language code.
        """
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

    def set_transcription_language(
        self,
        language,
        save=True,
    ):
        """
        Change speech-recognition language immediately.

        Supported values:
            en   - English
            ru   - Russian
            auto - automatic detection
        """
        normalized = self.normalize_language(
            language
        )

        self.transcription_language = (
            normalized
        )

        if save:
            self.save_voice_language(
                normalized
            )

        return normalized

    @staticmethod
    def save_voice_language(
        language,
    ):
        """
        Save only the language preference without overwriting
        existing AI settings or the API key.
        """
        settings = {}

        if SETTINGS_FILE.exists():
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
                    settings = loaded

            except (
                OSError,
                json.JSONDecodeError,
            ) as error:
                print(
                    "Voice language settings read error: "
                    f"{type(error).__name__}: {error}"
                )

        settings["voice_language"] = (
            VoiceService.normalize_language(
                language
            )
        )

        try:
            SETTINGS_FILE.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temporary_file = (
                SETTINGS_FILE.with_suffix(
                    ".json.tmp"
                )
            )

            with temporary_file.open(
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    settings,
                    file,
                    ensure_ascii=False,
                    indent=2,
                )
                file.write("\n")

            os.replace(
                temporary_file,
                SETTINGS_FILE,
            )

        except OSError as error:
            print(
                "Voice language settings save error: "
                f"{type(error).__name__}: {error}"
            )

    def record_and_transcribe(self, duration=None):
        record_duration = duration if duration is not None else self.record_seconds
        record_duration = max(1, min(float(record_duration), 30))

        audio_data = self.record_audio(record_duration)
        temporary_path = self.save_temporary_wav(audio_data)

        try:
            return self.transcribe_file(temporary_path)
        finally:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    def record_audio(self, duration):
        frame_count = int(duration * self.sample_rate)

        try:
            recording = sd.rec(
                frame_count,
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
            )
            sd.wait()
        except Exception as error:
            raise RuntimeError(
                "Unable to record from the microphone. "
                "Check microphone permission and the selected input device. "
                f"Details: {error}"
            ) from error

        if recording is None or recording.size == 0:
            raise RuntimeError("No microphone audio was recorded.")

        maximum_level = int(np.max(np.abs(recording)))
        if maximum_level < 40:
            raise RuntimeError(
                "The recording was silent. Check the microphone or speak louder."
            )

        return recording

    def save_temporary_wav(self, audio_data):
        temporary_file = tempfile.NamedTemporaryFile(
            prefix="m12_voice_",
            suffix=".wav",
            delete=False,
        )
        temporary_path = Path(temporary_file.name)
        temporary_file.close()

        try:
            with wave.open(str(temporary_path), "wb") as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(2)
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(audio_data.tobytes())
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

        return temporary_path

    def transcribe_file(self, audio_path):
        try:
            with audio_path.open("rb") as audio_file:
                request = {
                    "model": self.transcription_model,
                    "file": audio_file,
                }

                if self.transcription_language != "auto":
                    request["language"] = (
                        self.transcription_language
                    )

                    language_name = {
                        "en": "English",
                        "ru": "Russian",
                    }.get(
                        self.transcription_language,
                        self.transcription_language,
                    )

                    request["prompt"] = (
                        f"The speaker is speaking {language_name}. "
                        f"Transcribe accurately in {language_name}."
                    )

                transcript = (
                    self.client.audio.transcriptions.create(
                        **request
                    )
                )
        except Exception as error:
            raise RuntimeError(
                "Voice transcription failed: "
                f"{error}"
            ) from error

        text = str(getattr(transcript, "text", "")).strip()
        if not text:
            raise RuntimeError("No speech was recognized.")

        return text

    def speak_text(self, text):
        """
        Generate and play speech. Call this from a worker thread.
        """
        if not self.voice_answers_enabled:
            return False

        speech_text = self.prepare_speech_text(text)
        if not speech_text:
            return False

        self.stop_speaking()

        temporary_file = tempfile.NamedTemporaryFile(
            prefix="m12_answer_",
            suffix=".mp3",
            delete=False,
        )
        speech_path = Path(temporary_file.name)
        temporary_file.close()

        try:
            self.create_speech_file(speech_text, speech_path)

            with self.playback_lock:
                self.playback_file = speech_path

            self.play_audio_file(speech_path)
            return True
        finally:
            with self.playback_lock:
                self.playback_process = None
                self.playback_file = None

            try:
                speech_path.unlink(missing_ok=True)
            except OSError:
                pass

    def create_speech_file(self, text, output_path):
        try:
            request = {
                "model": self.speech_model,
                "voice": self.speech_voice,
                "input": text,
                "response_format": "mp3",
            }

            if self.speech_instructions:
                request["instructions"] = self.speech_instructions

            with self.client.audio.speech.with_streaming_response.create(
                **request
            ) as response:
                response.stream_to_file(output_path)

        except Exception as error:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass

            raise RuntimeError(
                "Voice answer generation failed: "
                f"{error}"
            ) from error

    def play_audio_file(self, audio_path):
        command = self.playback_command(audio_path)
        if not command:
            raise RuntimeError("No supported audio player was found.")

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            with self.playback_lock:
                self.playback_process = process

            process.wait()
        except Exception as error:
            raise RuntimeError(
                "Unable to play the voice answer: "
                f"{error}"
            ) from error

    @staticmethod
    def playback_command(audio_path):
        path_text = str(audio_path)

        if os.name == "nt":
            escaped_path = path_text.replace("'", "''")
            return [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Add-Type -AssemblyName presentationCore; "
                    "$player = New-Object System.Windows.Media.MediaPlayer; "
                    f"$player.Open([Uri]'{escaped_path}'); "
                    "$player.Play(); "
                    "while ($player.NaturalDuration.HasTimeSpan -eq $false) "
                    "{ Start-Sleep -Milliseconds 100 }; "
                    "Start-Sleep -Milliseconds "
                    "($player.NaturalDuration.TimeSpan.TotalMilliseconds); "
                    "$player.Close();"
                ),
            ]

        if hasattr(os, "uname") and os.uname().sysname == "Darwin":
            return ["afplay", path_text]

        candidates = [
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path_text],
            ["mpg123", "-q", path_text],
            ["paplay", path_text],
        ]

        for command in candidates:
            if VoiceService.command_exists(command[0]):
                return command

        return None

    def stop_speaking(self):
        with self.playback_lock:
            process = self.playback_process

        if process is None or process.poll() is not None:
            return False

        try:
            process.terminate()
            try:
                process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                process.kill()
            return True
        except Exception as error:
            print(
                "Stop speaking error: "
                f"{type(error).__name__}: {error}"
            )
            return False
        finally:
            with self.playback_lock:
                self.playback_process = None

    def is_speaking(self):
        with self.playback_lock:
            process = self.playback_process

        return process is not None and process.poll() is None

    @staticmethod
    def prepare_speech_text(text):
        speech_text = str(text).strip()
        if not speech_text:
            return ""

        for token in ("[b]", "[/b]", "[i]", "[/i]", "[u]", "[/u]", "```"):
            speech_text = speech_text.replace(token, "")

        speech_text = " ".join(speech_text.split())
        return speech_text[:4000]

    @staticmethod
    def command_exists(command):
        for folder in os.getenv("PATH", "").split(os.pathsep):
            candidate = Path(folder) / command
            if candidate.exists() and os.access(candidate, os.X_OK):
                return True
        return False

    @staticmethod
    def available_microphones():
        microphones = []

        try:
            devices = sd.query_devices()

            for index, device in enumerate(devices):
                input_channels = int(device.get("max_input_channels", 0))
                if input_channels <= 0:
                    continue

                microphones.append(
                    {
                        "index": index,
                        "name": str(device.get("name", "Unknown microphone")),
                        "channels": input_channels,
                    }
                )

        except Exception as error:
            print(f"Microphone list error: {error}")

        return microphones
