#!/bin/bash

set -e

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$HOME/m12_android_tools:$PATH"

mkdir -p /tmp/m12-empty-pkgconfig
export PKG_CONFIG_PATH=/tmp/m12-empty-pkgconfig
export PKG_CONFIG_LIBDIR=/tmp/m12-empty-pkgconfig

echo "========================================"
echo "M12 OS Android Build Environment"
echo "========================================"
echo "JAVA_HOME=$JAVA_HOME"
java -version
javac -version
echo "sdl2-config: $(which sdl2-config)"
echo "Python: $(which python)"
echo "========================================"

buildozer android debug
