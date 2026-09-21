from pathlib import Path
import time

import numpy as np
import sounddevice as sd
import sherpa_onnx


BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = (
    BASE_DIR
    / "models"
    / "speaker"
    / "wespeaker_en_voxceleb_resnet34.onnx"
)
PROFILE_DIR = BASE_DIR / "data" / "voice_profiles"
PROFILE_PATH = PROFILE_DIR / "owner.npy"

SAMPLE_RATE = 16000
RECORD_SECONDS = 5
NUM_SAMPLES = 5

PROFILE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

if not MODEL_PATH.exists():
    raise FileNotFoundError(
        f"Speaker model not found: {MODEL_PATH}"
    )

config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
    model=str(MODEL_PATH),
    num_threads=2,
    debug=False,
    provider="cpu",
)

if not config.validate():
    raise RuntimeError(
        f"Invalid speaker embedding config: {config}"
    )

extractor = sherpa_onnx.SpeakerEmbeddingExtractor(
    config
)

embeddings = []

print()
print("M12 Owner Voice Enrollment")
print("==========================")
print(f"We will record {NUM_SAMPLES} samples.")
print(f"Each sample is {RECORD_SECONDS} seconds.")
print()
print("Speak naturally.")
print("Recommended:")
print("  Sample 1: Russian")
print("  Sample 2: Russian")
print("  Sample 3: English")
print("  Sample 4: English")
print("  Sample 5: mixed Russian/English")
print()

for i in range(NUM_SAMPLES):
    input(
        f"Press ENTER when ready for sample "
        f"{i + 1}/{NUM_SAMPLES}..."
    )

    print("Recording starts in:")

    for n in (3, 2, 1):
        print(n)
        time.sleep(1)

    print("SPEAK NOW")

    audio = sd.rec(
        int(RECORD_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
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
        sample_rate=SAMPLE_RATE,
        waveform=samples,
    )

    stream.input_finished()

    if not extractor.is_ready(stream):
        raise RuntimeError(
            f"Speaker embedding is not ready "
            f"for sample {i + 1}"
        )

    embedding = extractor.compute(stream)

    embedding = np.asarray(
        embedding,
        dtype=np.float32,
    )

    norm = np.linalg.norm(
        embedding
    )

    if norm <= 0:
        raise RuntimeError(
            f"Invalid embedding for sample "
            f"{i + 1}"
        )

    embedding = embedding / norm

    embeddings.append(
        embedding
    )

    print(
        f"Sample {i + 1} complete."
    )
    print()

owner_embedding = np.mean(
    np.stack(
        embeddings
    ),
    axis=0,
)

owner_norm = np.linalg.norm(
    owner_embedding
)

if owner_norm <= 0:
    raise RuntimeError(
        "Unable to create owner voice profile."
    )

owner_embedding = (
    owner_embedding
    / owner_norm
)

np.save(
    PROFILE_PATH,
    owner_embedding.astype(
        np.float32
    ),
)

print()
print("DONE")
print("Owner profile saved to:")
print(PROFILE_PATH)
print(
    f"Embedding dimensions: "
    f"{owner_embedding.shape}"
)
