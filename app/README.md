# The phone app

Mesh Contingency for phones (`com.meshcontingency`): users do what they'd
type to the node (join, check in, the mailbox, email, the weather) from
screens, over Bluetooth to their own MeshCore radio; plus chat with their
contacts and channels, and their radio's settings. It talks to the node only
through the radio, as direct messages. The plan, and what each step adds, is
in [`docs/plans/mobile-app.md`](../docs/plans/mobile-app.md).

An Angular app made into an Android app with [Capacitor](https://capacitorjs.com/);
`android/` is the Android project Capacitor made, committed as it expects.
The palette, type, panels and buttons are the web console's own stylesheet
(`../console/src/styles.scss`, in `angular.json`); `src/app/icon.ts` is a
copy of the console's icons, which `tests/test_app.py` keeps the same.

## How it talks to the radio

`src/app/radio/`: `Radio` (the service the screens use: connect, reconnect,
the radio's name and battery) over `CapacitorBleConnection`, a meshcore.js
`Connection` on the Bluetooth plugin, writing one frame at a time. The
plugin is behind the `BLE` token, so the tests use `FakeBle`, a pretend
companion radio that answers frames as a real one does.

`src/app/node/`: `NodeLink` sends the node commands through the radio, one
at a time, and collects its answers (numbered parts put back in order) and
notices; `replies.ts` reads them. What it reads is pinned in
`../tests/fixtures/app_replies.json`, which `replies.spec.ts` and the bot's
`tests/test_app_replies.py` both check, so a reply can't change on one side
only.

`src/app/radio/presets.json` is a copy of the bot's MeshCore presets
(`mesh_contingency/radio_presets.py`) for the Radio tab, which
`tests/test_app.py` also keeps the same.

Android asks only for Nearby devices (location on Android 11 and older,
which needed it to scan). Release builds have no internet permission; the
debug manifest (`android/app/src/debug/`) adds it for live reload.

## Working on it

```sh
npm ci                 # once, and after package-lock.json changes
npm start              # in a browser at http://127.0.0.1:4200 (no Bluetooth there)
npm run demo           # the same, on the tests' fake radio with made-up contacts and chats
npm test               # unit tests (Vitest)
npm run format:check   # formatting (Prettier); npm run format fixes it
npm run build          # the web build, into dist/
```

## Trying it on this computer

An Android emulator runs the app as a phone would, from `scripts/android.sh`
(after the SDK below is set up):

```sh
npm run emulator:setup   # once: the emulator and a virtual phone, "mesh-contingency" (about 1.5 GB)
npm run android:run      # build, start the virtual phone if needed, install the app and open it
npm run android:live     # the same, then reload on the phone as you edit src/ (Ctrl+C stops)
npm run emulator         # just start the virtual phone
```

The virtual phone keeps running after these finish, and the computer's
keyboard types into it; close its window to stop it. Java 21 is found in
sdkman when `JAVA_HOME` isn't set to 17 or 21. A phone plugged in over USB
with USB debugging on is used instead of the emulator. After
`android:live`, run `android:run` to put the built app back: live mode
points the app at the dev server, which is gone once it stops.

The emulator's Bluetooth is pretend, with no MeshCore radio near it: it
asks for the permission and scans, but finding a radio needs a real phone
and radio. Everything else runs there. `npm start` (a browser at
http://127.0.0.1:4200) is quicker still for screens alone, and `npm run
demo` shows them with a radio connected: the fake one the tests use
(`src/app/demo.fake.ts`, swapped in for `src/app/demo.ts` by angular.json's
demo configuration), slow to list its contacts as a real one is. Size the
browser window to try a phone's width or a tablet's.

## Building for Android

Needs Java 21 and the Android SDK (platform 36). On Linux, without Android
Studio:

```sh
# Java 21, e.g. with sdkman: sdk install java 21.0.12+1.1-tem
# The SDK's command-line tools from https://developer.android.com/studio#command-line-tools-only,
# unzipped to ~/Android/Sdk/cmdline-tools/latest, then:
export ANDROID_HOME=~/Android/Sdk
yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses
$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager "platforms;android-36" "platform-tools" "build-tools;36.0.0"
```

Then, with `JAVA_HOME` pointing at Java 21:

```sh
npm run android                        # build the web app and copy it into android/
(cd android && ./gradlew assembleDebug)
# -> android/app/build/outputs/apk/debug/app-debug.apk
```

CI builds the same APK on every pull request (the **Android build** job's
`mesh-contingency-debug-apk` artifact), so a computer with the SDK isn't
needed just to try it.

## Installing it on a phone

The debug APK installs on any Android 7 (API 24) or newer phone:

- **Over USB:** turn on Developer options and USB debugging on the phone,
  then `$ANDROID_HOME/platform-tools/adb install -r app-debug.apk`.
- **Without a cable:** copy the APK to the phone and open it; Android asks
  to allow installing apps from that source the first time.

It's a debug build, for trying it out. Debug builds are all signed with
the same key, `android/app/debug.keystore` in the repo, so a newer one (from
CI or any computer) installs over the last and the app keeps its data. That
key is public, so it's only for test builds; releases get their own,
private key. A build from before the shared key (2026-10-25) has to be
uninstalled once first.
