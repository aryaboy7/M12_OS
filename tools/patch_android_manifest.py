#!/usr/bin/env python3

from pathlib import Path
import sys


RECEIVER_BLOCK = """        <!-- M12 OS native Timer receiver -->
        <receiver
            android:name="com.m12os.m12os.TimerAlarmReceiver"
            android:enabled="true"
            android:exported="false" />

        <!-- M12 OS native Calendar Event receiver -->
        <receiver
            android:name="com.m12os.m12os.EventAlarmReceiver"
            android:enabled="true"
            android:exported="false" />

        <!-- M12 OS native Clock Alarm receiver -->
        <receiver
            android:name="com.m12os.m12os.ClockAlarmReceiver"
            android:enabled="true"
            android:exported="false" />

        <!-- M12 OS native Spotify control receiver -->
        <receiver
            android:name="com.m12os.m12os.SpotifyControlReceiver"
            android:enabled="true"
            android:exported="false" />

"""

THREE_RECEIVER_BLOCK = """        <!-- M12 OS native Timer receiver -->
        <receiver
            android:name="com.m12os.m12os.TimerAlarmReceiver"
            android:enabled="true"
            android:exported="false" />

        <!-- M12 OS native Calendar Event receiver -->
        <receiver
            android:name="com.m12os.m12os.EventAlarmReceiver"
            android:enabled="true"
            android:exported="false" />

        <!-- M12 OS native Clock Alarm receiver -->
        <receiver
            android:name="com.m12os.m12os.ClockAlarmReceiver"
            android:enabled="true"
            android:exported="false" />

"""

TIMER_ONLY_BLOCK = """        <!-- M12 OS native Timer receiver -->
        <receiver
            android:name="com.m12os.m12os.TimerAlarmReceiver"
            android:enabled="true"
            android:exported="false" />

"""


def patch_manifest(path: Path) -> bool:
    if not path.exists():
        print(f"[SKIP] Not found: {path}")
        return False

    text = path.read_text(encoding="utf-8")

    required = (
        "com.m12os.m12os.TimerAlarmReceiver",
        "com.m12os.m12os.EventAlarmReceiver",
        "com.m12os.m12os.ClockAlarmReceiver",
        "com.m12os.m12os.SpotifyControlReceiver",
    )

    if all(item in text for item in required):
        print(f"[OK] Already patched: {path}")
        return False

    if THREE_RECEIVER_BLOCK in text:
        text = text.replace(
            THREE_RECEIVER_BLOCK,
            RECEIVER_BLOCK,
            1,
        )

    elif TIMER_ONLY_BLOCK in text:
        text = text.replace(
            TIMER_ONLY_BLOCK,
            RECEIVER_BLOCK,
            1,
        )

    else:
        marker = """        </activity>

"""
        if marker not in text:
            raise RuntimeError(
                f"Could not find </activity> insertion point in {path}"
            )

        text = text.replace(
            marker,
            marker + RECEIVER_BLOCK,
            1,
        )

    path.write_text(
        text,
        encoding="utf-8",
    )

    verify = path.read_text(
        encoding="utf-8"
    )

    missing = [
        item
        for item in required
        if item not in verify
    ]

    if missing:
        raise RuntimeError(
            f"Patch verification failed for {path}. Missing: {missing}"
        )

    print(f"[PATCHED] {path}")
    return True


def main() -> int:
    project_root = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )

    p4a_template = (
        project_root
        / ".buildozer"
        / "android"
        / "platform"
        / "python-for-android"
        / "pythonforandroid"
        / "bootstraps"
        / "_sdl_common"
        / "build"
        / "templates"
        / "AndroidManifest.tmpl.xml"
    )

    bootstrap_template = (
        project_root
        / ".buildozer"
        / "android"
        / "platform"
        / "build-arm64-v8a"
        / "build"
        / "bootstrap_builds"
        / "sdl2"
        / "templates"
        / "AndroidManifest.tmpl.xml"
    )

    print("M12 OS Android manifest patcher")
    print(f"Project root: {project_root}")
    print()

    changed = 0

    for target in (
        p4a_template,
        bootstrap_template,
    ):
        try:
            if patch_manifest(target):
                changed += 1
        except Exception as error:
            print(
                f"[ERROR] {target}: "
                f"{type(error).__name__}: {error}"
            )
            return 1

    print()

    if changed:
        print(
            f"Done. Patched {changed} "
            "manifest template(s)."
        )
    else:
        print(
            "Done. No changes were required."
        )

    print()
    print("Next command:")
    print("  buildozer android debug")

    return 0


if __name__ == "__main__":
    sys.exit(main())