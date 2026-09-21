import time
from pathlib import Path

import sounddevice as sd

from services.speaker_verification_service import (
    SpeakerVerificationService,
)
from services.voice_gate import VoiceGate


SAMPLE_RATE = 24000
CHANNELS = 1
BLOCK_MS = 20
BLOCK_FRAMES = int(
    SAMPLE_RATE * BLOCK_MS / 1000
)


def main():
    verifier = SpeakerVerificationService(
        owner_threshold=0.80
    )

    if not verifier.available:
        raise RuntimeError(
            verifier.last_error
        )

    gate = VoiceGate(
        speaker_verifier=verifier,
        owner_threshold=0.80,
        output_sample_rate=SAMPLE_RATE,
    )

    if not gate.available:
        raise RuntimeError(
            gate.last_error
        )

    print()
    print("M12 Voice Gate Test")
    print("===================")
    print()
    print("This test does NOT connect to OpenAI.")
    print("It only tests local VAD + speaker verification.")
    print()
    print("Commands:")
    print("  g + ENTER  -> arm one guest turn")
    print("  q + ENTER  -> quit")
    print()
    print("Speak normally. After each completed utterance")
    print("you should see OWNER, GUEST, or REJECTED.")
    print()

    running = True

    def callback(
        indata,
        frames,
        time_info,
        status,
    ):
        if status:
            print(
                f"[Audio] {status}"
            )

        try:
            results = gate.process_pcm16le(
                bytes(indata),
                SAMPLE_RATE,
            )

            for result in results:
                score = result["score"]

                score_text = (
                    f"{score:.4f}"
                    if score is not None
                    else "n/a"
                )

                role = str(
                    result["role"]
                ).upper()

                print()
                print(
                    f">>> {role} "
                    f"score={score_text} "
                    f"duration={result['duration']:.2f}s"
                )

                if result["accepted"]:
                    print(
                        "    ACCEPTED — would be sent to Realtime"
                    )
                else:
                    print(
                        "    REJECTED — would NOT be sent to Realtime"
                    )

                print()

        except Exception as error:
            print(
                "[VoiceGate test error] "
                f"{type(error).__name__}: {error}"
            )

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_FRAMES,
        channels=CHANNELS,
        dtype="int16",
        callback=callback,
    ):
        while running:
            command = input().strip().lower()

            if command == "g":
                gate.authorize_guest_once()
                print(
                    "Guest mode armed for exactly one non-owner utterance."
                )

            elif command == "q":
                running = False

            elif command:
                print(
                    "Use g to arm guest or q to quit."
                )


if __name__ == "__main__":
    main()
