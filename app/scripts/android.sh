#!/usr/bin/env bash
# Run the phone app on an Android emulator or a phone plugged in over USB.
#
#   scripts/android.sh setup     make the emulator's virtual phone (once)
#   scripts/android.sh emulator  start the virtual phone
#   scripts/android.sh run       build the app, install it and open it
#   scripts/android.sh live      the same, but reloading as you edit src/
#
# A phone plugged in with USB debugging on is used instead of the emulator.
# npm run emulator / android:run / android:live call these. See README.md.
set -euo pipefail

SCRIPT="$(realpath "$0")"
cd "$(dirname "$SCRIPT")/.."

AVD=mesh-contingency
IMAGE="system-images;android-36;google_apis;x86_64"
DEVICE=pixel_9a
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"

# The Android Gradle plugin wants Java 17 or 21; use 21 from sdkman when the
# default java is another version.
java_major() { "$1" -version 2>&1 | sed -n 's/.*version "\([0-9]*\).*/\1/p' | head -1; }
if [[ -z "${JAVA_HOME:-}" ]] || [[ ! "$(java_major "$JAVA_HOME/bin/java")" =~ ^(17|21)$ ]]; then
  found=$(ls -d "$HOME"/.sdkman/candidates/java/21* 2>/dev/null | sort -V | tail -1 || true)
  [[ -n "$found" ]] || { echo "Java 21 is needed (e.g. sdk install java 21.0.12+1.1-tem); set JAVA_HOME to it." >&2; exit 1; }
  export JAVA_HOME="$found"
fi

ADB="$ANDROID_HOME/platform-tools/adb"
EMULATOR="$ANDROID_HOME/emulator/emulator"
SDKMANAGER="$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"
AVDMANAGER="$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager"
[[ -x "$ADB" ]] || { echo "No Android SDK at $ANDROID_HOME (see README.md, Building for Android)." >&2; exit 1; }

setup() {
  yes | "$SDKMANAGER" --licenses >/dev/null
  "$SDKMANAGER" emulator "$IMAGE"
  if ! "$EMULATOR" -list-avds | grep -qx "$AVD"; then
    echo no | "$AVDMANAGER" create avd -n "$AVD" -k "$IMAGE" -d "$DEVICE"
    # Type into the virtual phone with the computer's keyboard.
    sed -i 's/^hw.keyboard=no/hw.keyboard=yes/' "$HOME/.android/avd/$AVD.avd/config.ini"
  fi
  echo "Virtual phone $AVD is ready: npm run emulator"
}

# The serial of a phone or emulator that's connected and booted, if any.
device() { "$ADB" devices | awk 'NR > 1 && $2 == "device" { print $1; exit }'; }

emulator() {
  if [[ -n "$(device)" ]]; then
    echo "Using $(device)."
    return
  fi
  "$EMULATOR" -list-avds | grep -qx "$AVD" || { echo "No virtual phone yet: npm run emulator:setup" >&2; exit 1; }
  echo "Starting the virtual phone $AVD..."
  # Its own session, so it keeps running when this script (or Ctrl+C) ends.
  setsid nohup "$EMULATOR" -avd "$AVD" -no-snapshot-save -no-boot-anim >/dev/null 2>&1 &
  "$ADB" wait-for-device
  until [[ "$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == 1 ]]; do sleep 2; done
  echo "Booted."
}

install_and_open() {
  (cd android && ./gradlew --quiet installDebug)
  "$ADB" -s "$(device)" shell am start -n com.meshcontingency/.MainActivity >/dev/null
  echo "Mesh Contingency is open on $(device)."
}

run() {
  emulator
  npx ng build
  npx cap sync android
  install_and_open
}

live() {
  emulator
  # The app loads the dev server (npm start) instead of its own files:
  # 10.0.2.2 is this computer as the emulator sees it; a phone on USB gets
  # the same port forwarded to it.
  "$ADB" -s "$(device)" reverse tcp:4200 tcp:4200 >/dev/null
  CAPACITOR_LIVE=http://localhost:4200 npx cap sync android
  install_and_open
  echo "Reloads as you edit src/. Ctrl+C stops; run npm run android:run afterwards to go back to the built app."
  npx ng serve --host 127.0.0.1 --port 4200
}

case "${1:-}" in
  setup) setup ;;
  emulator) emulator ;;
  run) run ;;
  live) live ;;
  *) sed -n '2,10p' "$SCRIPT" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
