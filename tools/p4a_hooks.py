from pathlib import Path


RECEIVERS_XML = """
        <!-- M12 OS native Timer receiver -->
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


def before_apk_assemble(toolchain):
    dist_dir = Path(toolchain.ctx.dist_dir)

    manifest = (
        dist_dir
	 /"m12os"
        / "src"
        / "main"
        / "AndroidManifest.xml"
    )

    if not manifest.exists():
        raise RuntimeError(
            f"M12 manifest hook: generated manifest not found: {manifest}"
        )

    text = manifest.read_text(encoding="utf-8")

    required = (
        "com.m12os.m12os.TimerAlarmReceiver",
        "com.m12os.m12os.EventAlarmReceiver",
        "com.m12os.m12os.ClockAlarmReceiver",
    )

    if all(name in text for name in required):
        print("[M12Hook] Native receivers already present.")
        return

    marker = "</application>"

    if marker not in text:
        raise RuntimeError(
            "M12 manifest hook: </application> not found"
        )

    text = text.replace(
        marker,
        RECEIVERS_XML + "\n    " + marker,
        1,
    )

    manifest.write_text(
        text,
        encoding="utf-8",
    )

    verify = manifest.read_text(encoding="utf-8")

    missing = [
        name
        for name in required
        if name not in verify
    ]

    if missing:
        raise RuntimeError(
            f"M12 manifest hook verification failed: {missing}"
        )

    print("[M12Hook] TimerAlarmReceiver added.")
    print("[M12Hook] EventAlarmReceiver added.")
    print("[M12Hook] ClockAlarmReceiver added.")
