from pathlib import Path
import math
import time

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_VAD_MODEL_PATH = (
    BASE_DIR
    / "models"
    / "speaker"
    / "silero_vad.onnx"
)

VAD_SAMPLE_RATE = 16000
DEFAULT_OWNER_THRESHOLD = 0.80


class VoiceGate:
    """
    Local speaker gate for M12 Voice.

    This class sits BEFORE OpenAI Realtime.

    Pipeline:
        microphone PCM
            -> local Silero VAD
            -> local owner verification
            -> owner / authorized guest decision
            -> accepted utterance returned to caller

    Rejected utterances are never returned to the Realtime layer.

    Input audio:
        signed 16-bit little-endian mono PCM

    Returned accepted audio:
        signed 16-bit little-endian mono PCM
        at ``output_sample_rate``

    Guest mode:
        The verified owner can arm one temporary guest turn by calling
        ``authorize_guest_once()``. The next completed non-owner utterance is
        accepted exactly once, then guest mode closes automatically.
    """

    def __init__(
        self,
        speaker_verifier,
        vad_model_path=None,
        owner_threshold=DEFAULT_OWNER_THRESHOLD,
        output_sample_rate=24000,
        guest_timeout_seconds=90.0,
        vad_threshold=0.25,
        min_silence_duration=0.55,
        min_speech_duration=0.45,
        max_speech_duration=20.0,
        num_threads=2,
        provider="cpu",
    ):
        self.speaker_verifier = speaker_verifier

        self.vad_model_path = Path(
            vad_model_path or DEFAULT_VAD_MODEL_PATH
        )

        self.owner_threshold = float(
            owner_threshold
        )

        self.output_sample_rate = int(
            output_sample_rate
        )

        self.guest_timeout_seconds = float(
            guest_timeout_seconds
        )

        self.vad_threshold = float(
            vad_threshold
        )

        self.min_silence_duration = float(
            min_silence_duration
        )

        self.min_speech_duration = float(
            min_speech_duration
        )

        self.max_speech_duration = float(
            max_speech_duration
        )

        self.num_threads = max(
            1,
            int(num_threads),
        )

        self.provider = str(
            provider or "cpu"
        )

        self.available = False
        self.last_error = ""

        self._np = None
        self._sherpa_onnx = None
        self._vad = None

        self._guest_turns_remaining = 0
        self._guest_access_until = 0.0

        self.last_score = None
        self.last_role = None

        self._initialize()

    @property
    def guest_armed(self):
        self._expire_guest_if_needed()

        return (
            self._guest_turns_remaining > 0
            and time.monotonic()
            <= self._guest_access_until
        )

    def _initialize(self):
        try:
            import numpy as np
            import sherpa_onnx

            if not self.vad_model_path.exists():
                raise FileNotFoundError(
                    f"Silero VAD model not found: "
                    f"{self.vad_model_path}"
                )

            if self.speaker_verifier is None:
                raise RuntimeError(
                    "Speaker verifier is required."
                )

            if not getattr(
                self.speaker_verifier,
                "available",
                False,
            ):
                raise RuntimeError(
                    "Speaker verifier is unavailable: "
                    + str(
                        getattr(
                            self.speaker_verifier,
                            "last_error",
                            "",
                        )
                    )
                )

            self._np = np
            self._sherpa_onnx = sherpa_onnx
            self._vad = self._create_vad()

            self.available = True
            self.last_error = ""

            print(
                "[VoiceGate] Ready "
                f"(owner threshold={self.owner_threshold:.2f})."
            )

        except Exception as error:
            self.available = False
            self.last_error = (
                f"{type(error).__name__}: {error}"
            )

            print(
                "[VoiceGate] Unavailable: "
                + self.last_error
            )

    def _create_vad(self):
        sherpa_onnx = self._sherpa_onnx

        config = sherpa_onnx.VadModelConfig()

        config.silero_vad.model = str(
            self.vad_model_path
        )

        config.silero_vad.threshold = (
            self.vad_threshold
        )

        config.silero_vad.min_silence_duration = (
            self.min_silence_duration
        )

        config.silero_vad.min_speech_duration = (
            self.min_speech_duration
        )

        config.silero_vad.max_speech_duration = (
            self.max_speech_duration
        )

        config.sample_rate = VAD_SAMPLE_RATE
        config.num_threads = self.num_threads
        config.provider = self.provider

        return sherpa_onnx.VoiceActivityDetector(
            config,
            buffer_size_in_seconds=30,
        )

    def reset(self):
        """
        Reset VAD and temporary guest state.
        """
        if self.available:
            self._vad = self._create_vad()

        self._guest_turns_remaining = 0
        self._guest_access_until = 0.0

        self.last_score = None
        self.last_role = None

    def authorize_guest_once(
        self,
    ):
        """
        Allow exactly one non-owner utterance for a limited time.
        """
        if not self.available:
            return False

        self._guest_turns_remaining = 1
        self._guest_access_until = (
            time.monotonic()
            + self.guest_timeout_seconds
        )

        print(
            "[VoiceGate] One guest turn armed "
            f"for {self.guest_timeout_seconds:.0f} seconds."
        )

        return True

    def cancel_guest_access(
        self,
    ):
        self._guest_turns_remaining = 0
        self._guest_access_until = 0.0

    def process_pcm16le(
        self,
        pcm_bytes,
        sample_rate,
    ):
        """
        Feed one microphone chunk into the local gate.

        Returns a list of decision dictionaries. Usually this is empty because
        the current utterance is still in progress. When local VAD completes an
        utterance, one result is returned:

            {
                "accepted": True/False,
                "role": "owner" | "guest" | "rejected",
                "score": float | None,
                "audio": bytes,
                "sample_rate": int,
                "duration": float,
            }

        ``audio`` is non-empty only for accepted utterances.
        """
        if not self.available:
            raise RuntimeError(
                self.last_error
                or "Voice gate is unavailable."
            )

        raw = bytes(
            pcm_bytes or b""
        )

        if len(raw) < 2:
            return []

        np = self._np

        samples = np.frombuffer(
            raw,
            dtype="<i2",
        ).astype(
            np.float32
        )

        if samples.size == 0:
            return []

        samples = samples / 32768.0

        source_rate = int(
            sample_rate
        )

        if source_rate <= 0:
            raise ValueError(
                "Invalid microphone sample rate."
            )

        if source_rate != VAD_SAMPLE_RATE:
            samples = self._resample_linear(
                samples,
                source_rate,
                VAD_SAMPLE_RATE,
            )

        self._vad.accept_waveform(
            samples
        )

        results = []

        while not self._vad.empty():
            segment = np.asarray(
                self._vad.front.samples,
                dtype=np.float32,
            ).copy()

            self._vad.pop()

            if segment.size == 0:
                continue

            decision = self._decide_segment(
                segment
            )

            results.append(
                decision
            )

        return results

    def _decide_segment(
        self,
        segment,
    ):
        np = self._np

        duration = (
            float(segment.size)
            / float(VAD_SAMPLE_RATE)
        )

        pcm16_16k = self._float_to_pcm16le(
            segment
        )

        is_owner = False
        score = None

        try:
            is_owner, score = (
                self.speaker_verifier.verify_pcm16le(
                    pcm16_16k,
                    VAD_SAMPLE_RATE,
                )
            )
        except Exception as error:
            print(
                "[VoiceGate] Speaker verification error: "
                f"{type(error).__name__}: {error}"
            )

        if score is not None:
            score = float(
                score
            )

        self.last_score = score

        if is_owner:
            role = "owner"
            accepted = True

            # The owner speaking does not consume guest permission. This lets
            # the owner clarify something while still allowing the next guest
            # utterance.
        elif self.guest_armed:
            role = "guest"
            accepted = True

            self._guest_turns_remaining = 0
            self._guest_access_until = 0.0
        else:
            role = "rejected"
            accepted = False

        self.last_role = role

        if accepted:
            output_samples = segment

            if self.output_sample_rate != VAD_SAMPLE_RATE:
                output_samples = self._resample_linear(
                    segment,
                    VAD_SAMPLE_RATE,
                    self.output_sample_rate,
                )

            output_audio = self._float_to_pcm16le(
                output_samples
            )
        else:
            output_audio = b""

        score_text = (
            f"{score:.4f}"
            if score is not None
            else "n/a"
        )

        print(
            "[VoiceGate] "
            f"{role} "
            f"(score={score_text}, "
            f"duration={duration:.2f}s)"
        )

        return {
            "accepted": accepted,
            "role": role,
            "score": score,
            "audio": output_audio,
            "sample_rate": (
                self.output_sample_rate
                if accepted
                else None
            ),
            "duration": duration,
        }

    def _expire_guest_if_needed(
        self,
    ):
        if (
            self._guest_turns_remaining > 0
            and time.monotonic()
            > self._guest_access_until
        ):
            self._guest_turns_remaining = 0
            self._guest_access_until = 0.0

            print(
                "[VoiceGate] Guest permission expired."
            )

    def _float_to_pcm16le(
        self,
        samples,
    ):
        np = self._np

        data = np.asarray(
            samples,
            dtype=np.float32,
        )

        data = np.clip(
            data,
            -1.0,
            1.0,
        )

        pcm = (
            data * 32767.0
        ).astype(
            "<i2"
        )

        return pcm.tobytes()

    def _resample_linear(
        self,
        samples,
        source_rate,
        target_rate,
    ):
        np = self._np

        if source_rate <= 0 or target_rate <= 0:
            raise ValueError(
                "Invalid sample rate."
            )

        if source_rate == target_rate:
            return samples.astype(
                np.float32,
                copy=False,
            )

        source_length = int(
            samples.size
        )

        if source_length <= 1:
            return samples.astype(
                np.float32,
                copy=False,
            )

        target_length = max(
            1,
            int(
                round(
                    source_length
                    * float(target_rate)
                    / float(source_rate)
                )
            ),
        )

        source_positions = np.linspace(
            0.0,
            1.0,
            num=source_length,
            endpoint=True,
            dtype=np.float64,
        )

        target_positions = np.linspace(
            0.0,
            1.0,
            num=target_length,
            endpoint=True,
            dtype=np.float64,
        )

        result = np.interp(
            target_positions,
            source_positions,
            samples,
        )

        return result.astype(
            np.float32
        )
