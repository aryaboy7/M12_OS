from pathlib import Path
import math


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_PATH = (
    BASE_DIR
    / "models"
    / "speaker"
    / "wespeaker_en_voxceleb_resnet34.onnx"
)
DEFAULT_PROFILE_PATH = (
    BASE_DIR
    / "data"
    / "voice_profiles"
    / "owner.npy"
)

DEFAULT_OWNER_THRESHOLD = 0.80
MODEL_SAMPLE_RATE = 16000


class SpeakerVerificationService:
    """
    M12 owner-speaker verification.

    The service intentionally loads numpy and sherpa_onnx lazily so platforms
    that do not yet package the speaker-recognition runtime can still start
    M12OS. In that case ``available`` is False and the caller can decide
    whether to fail open or fail closed.

    Input audio is signed 16-bit little-endian mono PCM. RealtimeVoiceService
    currently captures at 24 kHz; this service resamples internally to the
    16 kHz expected by the WeSpeaker model.
    """

    def __init__(
        self,
        model_path=None,
        profile_path=None,
        owner_threshold=DEFAULT_OWNER_THRESHOLD,
        num_threads=2,
        provider="cpu",
    ):
        self.model_path = Path(
            model_path or DEFAULT_MODEL_PATH
        )
        self.profile_path = Path(
            profile_path or DEFAULT_PROFILE_PATH
        )
        self.owner_threshold = float(
            owner_threshold
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
        self.last_score = None

        self._np = None
        self._extractor = None
        self._owner_embedding = None

        self._initialize()

    def _initialize(self):
        try:
            import numpy as np
            import sherpa_onnx

            if not self.model_path.exists():
                raise FileNotFoundError(
                    f"Speaker model not found: {self.model_path}"
                )

            if not self.profile_path.exists():
                raise FileNotFoundError(
                    f"Owner voice profile not found: {self.profile_path}"
                )

            config = (
                sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                    model=str(self.model_path),
                    num_threads=self.num_threads,
                    debug=False,
                    provider=self.provider,
                )
            )

            if not config.validate():
                raise RuntimeError(
                    f"Invalid speaker embedding config: {config}"
                )

            extractor = (
                sherpa_onnx.SpeakerEmbeddingExtractor(
                    config
                )
            )

            owner = np.load(
                self.profile_path
            ).astype(
                np.float32
            )

            owner = owner.reshape(-1)

            norm = float(
                np.linalg.norm(owner)
            )

            if not math.isfinite(norm) or norm <= 0:
                raise RuntimeError(
                    "Owner voice profile is invalid."
                )

            owner = owner / norm

            self._np = np
            self._extractor = extractor
            self._owner_embedding = owner
            self.available = True
            self.last_error = ""

            print(
                "[SpeakerVerify] Owner verification ready "
                f"(threshold={self.owner_threshold:.2f})."
            )

        except Exception as error:
            self.available = False
            self.last_error = (
                f"{type(error).__name__}: {error}"
            )

            print(
                "[SpeakerVerify] Unavailable: "
                + self.last_error
            )

    def reload_profile(self):
        """
        Reload the owner profile and speaker model state.

        Useful after re-enrollment without restarting all of M12OS.
        """
        self.available = False
        self.last_error = ""
        self.last_score = None
        self._np = None
        self._extractor = None
        self._owner_embedding = None
        self._initialize()
        return self.available

    def verify_pcm16le(
        self,
        pcm_bytes,
        sample_rate,
    ):
        """
        Return ``(is_owner, score)`` for mono PCM16LE audio.

        ``score`` is cosine similarity against the enrolled owner profile.
        """
        if not self.available:
            raise RuntimeError(
                self.last_error
                or "Speaker verification is unavailable."
            )

        audio_bytes = bytes(
            pcm_bytes or b""
        )

        if len(audio_bytes) < 2:
            raise ValueError(
                "Speaker verification received no audio."
            )

        np = self._np

        samples = np.frombuffer(
            audio_bytes,
            dtype="<i2",
        ).astype(
            np.float32
        )

        if samples.size == 0:
            raise ValueError(
                "Speaker verification received no samples."
            )

        samples = samples / 32768.0

        samples = self._trim_silence(
            samples
        )

        if samples.size < int(
            0.35 * float(sample_rate)
        ):
            raise ValueError(
                "Speaker sample is too short."
            )

        if int(sample_rate) != MODEL_SAMPLE_RATE:
            samples = self._resample_linear(
                samples=samples,
                source_rate=int(sample_rate),
                target_rate=MODEL_SAMPLE_RATE,
            )

        stream = (
            self._extractor.create_stream()
        )

        stream.accept_waveform(
            sample_rate=MODEL_SAMPLE_RATE,
            waveform=samples,
        )
        stream.input_finished()

        if not self._extractor.is_ready(
            stream
        ):
            raise RuntimeError(
                "Speaker embedding is not ready "
                "for this utterance."
            )

        embedding = self._extractor.compute(
            stream
        )

        embedding = np.asarray(
            embedding,
            dtype=np.float32,
        ).reshape(-1)

        norm = float(
            np.linalg.norm(embedding)
        )

        if not math.isfinite(norm) or norm <= 0:
            raise RuntimeError(
                "Speaker embedding is invalid."
            )

        embedding = embedding / norm

        score = float(
            np.dot(
                self._owner_embedding,
                embedding,
            )
        )

        self.last_score = score

        return (
            score >= self.owner_threshold,
            score,
        )

    def _trim_silence(
        self,
        samples,
    ):
        """
        Remove obvious leading/trailing silence using a conservative RMS gate.

        This is not speaker VAD; it only prevents long silence padding from
        dominating a short verification utterance.
        """
        np = self._np

        if samples.size == 0:
            return samples

        frame_size = int(
            MODEL_SAMPLE_RATE * 0.02
        )

        if frame_size <= 0:
            return samples

        # The incoming stream may still be 24 kHz. Use approximately 20 ms.
        # Infer frame size from signal duration only after using the caller's
        # rate would complicate this helper, so 320 samples is conservative.
        frame_size = 320

        frame_count = int(
            math.ceil(
                samples.size / frame_size
            )
        )

        rms_values = []

        for index in range(frame_count):
            start = index * frame_size
            end = min(
                samples.size,
                start + frame_size,
            )
            frame = samples[start:end]

            if frame.size == 0:
                rms_values.append(0.0)
                continue

            rms = float(
                np.sqrt(
                    np.mean(
                        frame * frame
                    )
                )
            )
            rms_values.append(rms)

        if not rms_values:
            return samples

        peak_rms = max(rms_values)

        if peak_rms <= 0:
            return samples

        threshold = max(
            0.004,
            peak_rms * 0.08,
        )

        active = [
            i
            for i, value in enumerate(rms_values)
            if value >= threshold
        ]

        if not active:
            return samples

        pad_frames = 5
        first = max(
            0,
            active[0] - pad_frames,
        )
        last = min(
            frame_count - 1,
            active[-1] + pad_frames,
        )

        start = first * frame_size
        end = min(
            samples.size,
            (last + 1) * frame_size,
        )

        return samples[start:end]

    def _resample_linear(
        self,
        samples,
        source_rate,
        target_rate,
    ):
        """
        Lightweight linear resampling; avoids a scipy dependency.
        """
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
