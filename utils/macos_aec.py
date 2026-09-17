import os
import platform
import subprocess
import threading
from pathlib import Path


class MacOSAECBackend:
    """
    Native macOS full-duplex AEC backend for M12.

    Transport contract:
        playback input:  24 kHz mono PCM16 little-endian
        microphone out:  24 kHz mono PCM16 little-endian

    The Swift helper owns both microphone capture and speaker playback through
    one AVAudioEngine with Apple Voice Processing enabled, giving the acoustic
    echo canceller the playback reference it needs.
    """

    def __init__(self, on_microphone_audio=None):
        self.on_microphone_audio = on_microphone_audio

        self._process = None
        self._reader_thread = None
        self._stderr_thread = None
        self._stop_event = threading.Event()
        self._write_lock = threading.Lock()

        base_dir = Path(__file__).resolve().parent
        self.source_path = base_dir / "macos_aec_bridge.swift"
        self.binary_path = base_dir / ".m12_mac_aec_bridge"

    @staticmethod
    def supported():
        return (
            platform.system() == "Darwin"
            and os.environ.get("ANDROID_ARGUMENT") is None
        )

    @property
    def is_running(self):
        process = self._process
        return (
            process is not None
            and process.poll() is None
            and not self._stop_event.is_set()
        )

    def _compile_if_needed(self):
        if not self.source_path.exists():
            raise RuntimeError(
                f"macOS AEC source is missing: {self.source_path}"
            )

        needs_compile = (
            not self.binary_path.exists()
            or self.binary_path.stat().st_mtime
            < self.source_path.stat().st_mtime
        )

        if not needs_compile:
            return

        completed = subprocess.run(
            [
                "swiftc",
                str(self.source_path),
                "-framework",
                "AVFoundation",
                "-o",
                str(self.binary_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60.0,
        )

        if completed.returncode != 0:
            raise RuntimeError(
                "Unable to compile macOS AEC helper:\n"
                + completed.stderr.strip()
            )

        if completed.stderr.strip():
            print(
                "[MacAEC] Swift compiler warnings:\n"
                + completed.stderr.strip()
            )

    def start(self):
        if not self.supported():
            return False

        if self.is_running:
            return True

        self._compile_if_needed()
        self._stop_event.clear()

        self._process = subprocess.Popen(
            [str(self.binary_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        self._reader_thread = threading.Thread(
            target=self._microphone_reader,
            name="M12MacAECMic",
            daemon=True,
        )
        self._reader_thread.start()

        self._stderr_thread = threading.Thread(
            target=self._stderr_reader,
            name="M12MacAECLog",
            daemon=True,
        )
        self._stderr_thread.start()

        return True

    def write_playback(self, audio_bytes):
        data = bytes(audio_bytes or b"")
        if not data:
            return

        process = self._process
        if (
            process is None
            or process.poll() is not None
            or process.stdin is None
        ):
            raise RuntimeError(
                "macOS AEC backend is not running."
            )

        with self._write_lock:
            process.stdin.write(data)
            process.stdin.flush()

    def _microphone_reader(self):
        process = self._process
        if process is None or process.stdout is None:
            return

        # M12 normally sends 20 ms input chunks:
        # 24,000 samples/s * .020 s * 2 bytes = 960 bytes.
        chunk_size = 960

        while not self._stop_event.is_set():
            data = process.stdout.read(chunk_size)

            if not data:
                break

            callback = self.on_microphone_audio
            if callback is None:
                continue

            try:
                callback(data)
            except Exception as error:
                print(
                    "[MacAEC] microphone callback error: "
                    f"{type(error).__name__}: {error}"
                )

    def _stderr_reader(self):
        process = self._process
        if process is None or process.stderr is None:
            return

        for raw_line in iter(process.stderr.readline, b""):
            if self._stop_event.is_set():
                break

            try:
                text = raw_line.decode(
                    "utf-8",
                    errors="replace",
                ).rstrip()
            except Exception:
                text = repr(raw_line)

            if text:
                print(text)

    def stop(self):
        self._stop_event.set()

        process = self._process
        self._process = None

        if process is not None:
            try:
                if process.stdin is not None:
                    process.stdin.close()
            except Exception:
                pass

            try:
                process.terminate()
                process.wait(timeout=2.0)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

        for thread in (
            self._reader_thread,
            self._stderr_thread,
        ):
            if (
                thread is not None
                and thread.is_alive()
                and thread is not threading.current_thread()
            ):
                thread.join(timeout=1.0)

        self._reader_thread = None
        self._stderr_thread = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
