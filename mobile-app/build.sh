#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Onyx Mobile App Build ==="

# 1. Check Node & dependencies
if [ ! -d "node_modules" ]; then
    echo "Installing npm dependencies..."
    npm ci || npm install
fi

# 2. Sync Capacitor Android
echo "Syncing Capacitor Android platform..."
npx cap sync android

# 3. Build APK with Gradle
cd android

if [ -z "${ANDROID_HOME:-}" ] && [ -d "$HOME/AppData/Local/Android/Sdk" ]; then
    export ANDROID_HOME="$HOME/AppData/Local/Android/Sdk"
fi

if [ -z "${JAVA_HOME:-}" ]; then
    if [ -d "/c/Program Files/Microsoft/jdk-21.0.12.101-hotspot" ]; then
        export JAVA_HOME="/c/Program Files/Microsoft/jdk-21.0.12.101-hotspot"
    elif [ -d "/c/Program Files/Android/Android Studio/jbr" ]; then
        export JAVA_HOME="/c/Program Files/Android/Android Studio/jbr"
    fi
fi

echo "Building Debug APK..."
./gradlew clean :app:assembleDebug

# Check if release keystore exists
HAS_KEYSTORE=false
if [ -f "keystore.properties" ]; then
    echo "keystore.properties found, building Release APK..."
    ./gradlew :app:assembleRelease
    HAS_KEYSTORE=true
fi

# 4. Copy artifacts to dist/
cd "$SCRIPT_DIR"
mkdir -p dist

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DEBUG_APK="android/app/build/outputs/apk/debug/app-debug.apk"

if [ -f "$DEBUG_APK" ]; then
    cp "$DEBUG_APK" "dist/OnyxWorkout-debug-${TIMESTAMP}.apk"
    cp "$DEBUG_APK" "dist/OnyxWorkout-debug-latest.apk"
    echo "Debug APK saved to: dist/OnyxWorkout-debug-latest.apk"
fi

if [ "$HAS_KEYSTORE" = true ]; then
    RELEASE_APK="android/app/build/outputs/apk/release/app-release.apk"
    if [ -f "$RELEASE_APK" ]; then
        cp "$RELEASE_APK" "dist/OnyxWorkout-release-${TIMESTAMP}.apk"
        cp "$RELEASE_APK" "dist/OnyxWorkout-release-latest.apk"
        echo "Release APK saved to: dist/OnyxWorkout-release-latest.apk"
    fi
fi

echo "=== Build Complete ==="
