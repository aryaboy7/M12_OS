from pathlib import Path
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

PROFILE_PATH = (
    BASE_DIR
    / "data"
    / "voice_profiles"
    / "owner.npy"
)

SAMPLE_RATE = 16000
RECORD_SECONDS = 5

config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
    model=str(MODEL_PATH),
    num_threads=2,
    debug=False,
    provider="cpu",
)

extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)

owner = np.load(PROFILE_PATH).astype(np.float32)
owner = owner / np.linalg.norm(owner)

print("Press ENTER, then speak naturally for 5 seconds.")
input()

audio = sd.rec(
    int(RECORD_SECONDS * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="float32",
)

sd.wait()

samples = np.asarray(audio[:, 0], dtype=np.float32)

stream = extractor.create_stream()
stream.accept_waveform(
    sample_rate=SAMPLE_RATE,
    waveform=samples,
)
stream.input_finished()

if not extractor.is_ready(stream):
    raise RuntimeError("Speaker embedding is not ready.")

embedding = np.asarray(
    extractor.compute(stream),
    dtype=np.float32,
)

embedding = embedding / np.linalg.norm(embedding)

score = float(np.dot(owner, embedding))

print()
print(f"Similarity score: {score:.4f}")
