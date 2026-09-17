"""Portable Linux WebRTC echo-cancel setup for M12 OS.

This module is intentionally independent of the Realtime audio engine.
It creates a per-user systemd service that loads PipeWire/PulseAudio's
module-echo-cancel only after the desktop audio stack is ready.

The setup is idempotent and does nothing on Android, macOS, or Windows.
"""

from __future__ import annotations

import os
import platform
import re
import shlex
import shutil
import subprocess
from pathlib import Path


SERVICE_NAME = "m12-echo-cancel.service"
SCRIPT_PATH = Path.home() / ".local" / "bin" / "m12-echo-cancel.sh"
SERVICE_PATH = Path.home() / ".config" / "systemd" / "user" / SERVICE_NAME
LEGACY_CONF = (
    Path.home()
    / ".config"
    / "pipewire"
    / "pipewire-pulse.conf.d"
    / "50-m12-echo-cancel.conf"
)
LEGACY_DISABLED = LEGACY_CONF.with_name(LEGACY_CONF.name + ".disabled")


class LinuxAECSetupError(RuntimeError):
    pass


def _is_desktop_linux() -> bool:
    if platform.system().lower() != "linux":
        return False
    # python-for-android reports a Linux kernel too, so exclude Android.
    if os.environ.get("ANDROID_ARGUMENT") or os.environ.get("ANDROID_PRIVATE"):
        return False
    return True


def _run(*args: str, timeout: float = 5.0, check: bool = True) -> str:
    completed = subprocess.run(
        list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=check,
    )
    return completed.stdout.strip()


def _pactl(*args: str, timeout: float = 5.0) -> str:
    return _run("pactl", *args, timeout=timeout)


def _extract_existing_masters() -> tuple[str, str]:
    """Return source_master/sink_master from an existing echo module, if any."""
    try:
        modules = _pactl("list", "modules", "short")
    except Exception:
        return "", ""

    for line in modules.splitlines():
        if "module-echo-cancel" not in line:
            continue
        source_match = re.search(r"\bsource_master=([^\s]+)", line)
        sink_match = re.search(r"\bsink_master=([^\s]+)", line)
        if source_match and sink_match:
            return source_match.group(1), sink_match.group(1)
    return "", ""


def _short_names(kind: str) -> list[str]:
    output = _pactl("list", "short", kind)
    names: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            names.append(parts[1].strip())
    return names


def _choose_source(default_source: str, sources: list[str]) -> str:
    def valid(name: str) -> bool:
        lowered = name.lower()
        return bool(name) and "echo-cancel" not in lowered and not lowered.endswith(".monitor")

    if valid(default_source):
        return default_source

    # Prefer ordinary ALSA capture devices, including USB microphones.
    for name in sources:
        if name.startswith("alsa_input.") and valid(name):
            return name
    # Then allow other physical/default capture technologies (for example bluez).
    for name in sources:
        if valid(name):
            return name
    return ""


def _choose_sink(default_sink: str, sinks: list[str]) -> str:
    def valid(name: str) -> bool:
        lowered = name.lower()
        return bool(name) and "echo-cancel" not in lowered

    if valid(default_sink):
        return default_sink

    # Prefer ordinary ALSA playback devices, including USB audio.
    for name in sinks:
        if name.startswith("alsa_output.") and valid(name):
            return name
    for name in sinks:
        if valid(name):
            return name
    return ""


def detect_physical_devices() -> tuple[str, str]:
    """Detect the physical/default capture and playback devices for this PC."""
    existing_source, existing_sink = _extract_existing_masters()
    if existing_source and existing_sink:
        return existing_source, existing_sink

    default_source = _pactl("get-default-source")
    default_sink = _pactl("get-default-sink")
    sources = _short_names("sources")
    sinks = _short_names("sinks")

    source = _choose_source(default_source, sources)
    sink = _choose_sink(default_sink, sinks)

    if not source:
        raise LinuxAECSetupError("No usable Linux microphone source was detected.")
    if not sink:
        raise LinuxAECSetupError("No usable Linux speaker sink was detected.")

    return source, sink


def _script_text(source: str, sink: str) -> str:
    q_source = shlex.quote(source)
    q_sink = shlex.quote(sink)
    return f'''#!/usr/bin/env bash
set -e

SOURCE={q_source}
SINK={q_sink}

# PipeWire may be started but not ready for pactl yet.
for i in {{1..20}}; do
    if pactl info >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Wait for the selected physical endpoints to exist.
for i in {{1..20}}; do
    if pactl list short sources | cut -f2 | grep -Fxq "$SOURCE" && \\
       pactl list short sinks   | cut -f2 | grep -Fxq "$SINK"; then
        break
    fi
    sleep 1
done

if ! pactl list modules short | grep -q "module-echo-cancel"; then
    pactl load-module module-echo-cancel \\
        aec_method=webrtc \\
        source_master="$SOURCE" \\
        sink_master="$SINK" \\
        source_name=echo-cancel-source \\
        sink_name=echo-cancel-sink
fi

# Give PipeWire a short moment to publish both virtual endpoints.
for i in {{1..20}}; do
    if pactl list short sources | cut -f2 | grep -Fxq echo-cancel-source && \\
       pactl list short sinks   | cut -f2 | grep -Fxq echo-cancel-sink; then
        break
    fi
    sleep 0.1
done

pactl set-default-source echo-cancel-source
pactl set-default-sink echo-cancel-sink
'''


def _service_text() -> str:
    return f'''[Unit]
Description=M12 WebRTC Echo Cancellation
After=pipewire.service pipewire-pulse.service wireplumber.service
Wants=pipewire.service pipewire-pulse.service wireplumber.service

[Service]
Type=oneshot
ExecStart=%h/.local/bin/m12-echo-cancel.sh
RemainAfterExit=yes

[Install]
WantedBy=default.target
'''


def _write_if_changed(path: Path, text: str, mode: int | None = None) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    old = None
    try:
        old = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        pass

    changed = old != text
    if changed:
        path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)
    return changed


def ensure_linux_aec_service(start_now: bool = True) -> dict:
    """Install/update and optionally start M12's Linux echo-cancel service.

    Returns a small status dictionary. Failures are raised as
    LinuxAECSetupError so callers can log them and continue without AEC.
    """
    if not _is_desktop_linux():
        return {"supported": False, "changed": False, "started": False}

    if shutil.which("pactl") is None:
        raise LinuxAECSetupError("pactl is not installed.")
    if shutil.which("systemctl") is None:
        raise LinuxAECSetupError("systemctl is not installed.")

    source, sink = detect_physical_devices()

    # Disable the old early PipeWire startup method if it exists. Loading the
    # module there proved unstable on Zorin; the delayed user service is stable.
    if LEGACY_CONF.exists():
        LEGACY_DISABLED.parent.mkdir(parents=True, exist_ok=True)
        if LEGACY_DISABLED.exists():
            LEGACY_DISABLED.unlink()
        LEGACY_CONF.rename(LEGACY_DISABLED)

    script_changed = _write_if_changed(
        SCRIPT_PATH,
        _script_text(source, sink),
        mode=0o755,
    )
    service_changed = _write_if_changed(
        SERVICE_PATH,
        _service_text(),
        mode=0o644,
    )

    _run("systemctl", "--user", "daemon-reload")
    _run("systemctl", "--user", "enable", SERVICE_NAME)

    started = False
    if start_now:
        # Starting an already active oneshot service is harmless. If the unit
        # definition or selected hardware changed, restart it to apply updates.
        action = "restart" if (script_changed or service_changed) else "start"
        _run("systemctl", "--user", action, SERVICE_NAME, timeout=30.0)
        started = True

    return {
        "supported": True,
        "changed": bool(script_changed or service_changed),
        "started": started,
        "source_master": source,
        "sink_master": sink,
        "script": str(SCRIPT_PATH),
        "service": str(SERVICE_PATH),
    }
