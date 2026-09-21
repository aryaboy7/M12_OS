from pathlib import Path
import time

import numpy as np


BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = (
    BASE_DIR
    / "models"
    / "speaker"
    / "wespeaker_en_voxceleb_resnet34.onnx"
)

DEFAULT_DESKTOP_PROFILE_PATH = (
    BASE_DIR
    / "data"
    / "voice_profiles"
    / "owner.npy"
)

SAMPLE_RATE = 16000
RECORD_SECONDS = 5
NUM_SAMPLES = 5


def get_owner_profile_path():
    """
    Return the device-local owner voice profile path.

    Desktop/macOS/Linux:
        <project>/data/voice_profiles/owner.npy

    Android:
        app-private files directory / voice_profiles / owner.npy
    """
    try:
        from kivy.utils import platform as kivy_platform
    except Exception:
        kivy_platform = ""

    if kivy_platform == "android":
        try:
            from jnius import autoclass

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            activity = PythonActivity.mActivity
            files_dir = activity.getFilesDir()

            return (
                Path(
                    str(
                        files_dir.getAbsolutePath()
                    )
                )
                / "voice_profiles"
                / "owner.npy"
            )

        except Exception as error:
            raise RuntimeError(
                "Unable to resolve Android private "
                "owner-profile path: "
                f"{type(error).__name__}: {error}"
            ) from error

    return DEFAULT_DESKTOP_PROFILE_PATH


class OwnerVoiceEnrollmentService:
    """
    Local owner voice enrollment.

    The service itself is UI-agnostic. A screen or test harness can provide
    callbacks for status/countdown/progress updates.
    """

    def __init__(
        self,
        model_path=None,
        profile_path=None,
        num_samples=NUM_SAMPLES,
        record_seconds=RECORD_SECONDS,
        sample_rate=SAMPLE_RATE,
        num_threads=2,
        provider="cpu",
    ):
        self.model_path = Path(
            model_path or MODEL_PATH
        )

        self.profile_path = Path(
            profile_path or get_owner_profile_path()
        )

        self.num_samples = max(
            1,
            int(num_samples),
        )

        self.record_seconds = max(
            1,
            int(record_seconds),
        )

        self.sample_rate = int(
            sample_rate
        )

        self.num_threads = max(
            1,
            int(num_threads),
        )

        self.provider = str(
            provider or "cpu"
        )

    def profile_exists(self):
        return self.profile_path.is_file()

    def enroll(
        self,
        *,
        on_status=None,
        on_countdown=None,
        on_sample_complete=None,
    ):
        """
        Record owner voice samples and save owner.npy.

        This method is blocking and should be called from a worker thread when
        used by the Kivy UI.
        """
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Speaker model not found: {self.model_path}"
            )

        try:
            import sounddevice as sd
            import sherpa_onnx
        except Exception as error:
            raise RuntimeError(
                "Owner enrollment dependencies are unavailable: "
                f"{type(error).__name__}: {error}"
            ) from error

        self.profile_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(
                self.model_path
            ),
            num_threads=self.num_threads,
            debug=False,
            provider=self.provider,
        )

        if not config.validate():
            raise RuntimeError(
                f"Invalid speaker embedding config: {config}"
            )

        extractor = sherpa_onnx.SpeakerEmbeddingExtractor(
            config
        )

        embeddings = []

        for index in range(self.num_samples):
            sample_number = index + 1

            if on_status is not None:
                on_status(
                    f"Get ready for sample "
                    f"{sample_number} of {self.num_samples}."
                )

            for number in (3, 2, 1):
                if on_countdown is not None:
                    on_countdown(
                        sample_number,
                        number,
                    )
                time.sleep(1.0)

            if on_status is not None:
                on_status(
                    f"Sample {sample_number}: SPEAK NOW"
                )

            audio = sd.rec(
                int(
                    self.record_seconds
                    * self.sample_rate
                ),
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
            )

            sd.wait()

            samples = np.asarray(
                audio[:, 0],
                dtype=np.float32,
            )

            stream = extractor.create_stream()

            stream.accept_waveform(
                sample_rate=self.sample_rate,
                waveform=samples,
            )

            stream.input_finished()

            if not extractor.is_ready(stream):
                raise RuntimeError(
                    "Speaker embedding is not ready for "
                    f"sample {sample_number}."
                )

            embedding = np.asarray(
                extractor.compute(stream),
                dtype=np.float32,
            ).reshape(-1)

            norm = float(
                np.linalg.norm(embedding)
            )

            if (
                not np.isfinite(norm)
                or norm <= 0
            ):
                raise RuntimeError(
                    "Invalid speaker embedding for "
                    f"sample {sample_number}."
                )

            embeddings.append(
                embedding / norm
            )

            if on_sample_complete is not None:
                on_sample_complete(
                    sample_number,
                    self.num_samples,
                )

            if index + 1 < self.num_samples:
                time.sleep(0.7)

        owner_embedding = np.mean(
            np.stack(embeddings),
            axis=0,
        )

        owner_norm = float(
            np.linalg.norm(owner_embedding)
        )

        if (
            not np.isfinite(owner_norm)
            or owner_norm <= 0
        ):
            raise RuntimeError(
                "Unable to create owner voice profile."
            )

        owner_embedding = (
            owner_embedding
            / owner_norm
        )

        temp_path = self.profile_path.with_suffix(
            ".tmp.npy"
        )

        np.save(
            temp_path,
            owner_embedding.astype(
                np.float32
            ),
        )

        check = np.load(
            temp_path
        )

        if (
            check.ndim != 1
            or check.size == 0
            or not np.all(
                np.isfinite(check)
            )
        ):
            try:
                temp_path.unlink()
            except Exception:
                pass

            raise RuntimeError(
                "Generated owner voice profile failed validation."
            )

        temp_path.replace(
            self.profile_path
        )

        if on_status is not None:
            on_status(
                "Owner voice enrollment completed."
            )

        return self.profile_path

    def ensure_profile_console(self):
        """
        Development helper used by command-line tests.
        """
        if self.profile_exists():
            print(
                "[OwnerEnrollment] Existing owner profile found:"
            )
            print(self.profile_path)
            return True

        print(
            "[OwnerEnrollment] Owner voice profile is missing."
        )
        print(
            "[OwnerEnrollment] Starting automatic enrollment."
        )

        def status(text):
            print(text)

        def countdown(sample_number, number):
            print(
                f"Sample {sample_number}: "
                f"recording starts in {number}..."
            )

        def sample_complete(sample_number, total):
            print(
                f"Sample {sample_number}/{total} complete."
            )

        self.enroll(
            on_status=status,
            on_countdown=countdown,
            on_sample_complete=sample_complete,
        )

        return self.profile_exists()
