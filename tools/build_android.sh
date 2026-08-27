#!/bin/bash

set -e

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$HOME/m12_android_tools:$PATH"

mkdir -p /tmp/m12-empty-pkgconfig
export PKG_CONFIG_PATH=/tmp/m12-empty-pkgconfig
export PKG_CONFIG_LIBDIR=/tmp/m12-empty-pkgconfig

PROJECT_ROOT="$HOME/Documents/M12_OS"
cd "$PROJECT_ROOT"

echo "========================================"
echo "M12 OS Android Build Environment"
echo "========================================"
echo "JAVA_HOME=$JAVA_HOME"
java -version
javac -version
echo "sdl2-config: $(which sdl2-config)"
echo "Python: $(which python)"
echo "========================================"

echo
echo "Patching Android manifest receivers..."
python tools/patch_android_manifest.py

P4A_MANIFEST_TEMPLATE="$PROJECT_ROOT/.buildozer/android/platform/python-for-android/pythonforandroid/bootstraps/_sdl_common/build/templates/AndroidManifest.tmpl.xml"

echo
echo "Verifying native Android receivers..."

for receiver in \
    TimerAlarmReceiver \
    EventAlarmReceiver \
    ClockAlarmReceiver
do
    if ! grep -q "com.m12os.m12os.$receiver" "$P4A_MANIFEST_TEMPLATE"; then
        echo "ERROR: $receiver is missing from Android manifest template."
        exit 1
    fi

    echo "OK: $receiver"
done

echo
echo "Building M12 OS Android APK..."
buildozer android debug

GENERATED_MANIFEST="$PROJECT_ROOT/.buildozer/android/platform/build-arm64-v8a/dists/m12os/src/main/AndroidManifest.xml"

echo
echo "Verifying generated APK manifest..."

if [ ! -f "$GENERATED_MANIFEST" ]; then
    echo "ERROR: Generated AndroidManifest.xml was not found."
    exit 1
fi

for receiver in \
    TimerAlarmReceiver \
    EventAlarmReceiver \
    ClockAlarmReceiver
do
    if ! grep -q "com.m12os.m12os.$receiver" "$GENERATED_MANIFEST"; then
        echo "ERROR: $receiver is missing from generated AndroidManifest.xml."
        exit 1
    fi

    echo "OK: $receiver"
done

echo
echo "========================================"
echo "M12 OS Android build completed successfully"
echo "All native alarm receivers are present"
echo "========================================"