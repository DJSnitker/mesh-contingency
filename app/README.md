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
the radio's name and battery) over either of two meshcore.js `Connection`s:
`CapacitorBleConnection`, on the Bluetooth plugin, writing one frame at a
time; or `UsbConnection`, a radio on a USB cable over Web Serial, with
meshcore.js's serial framing. Web Serial is in Chromium on a computer (the
desktop app, roadmap item 18, or Chrome and Edge), not in Android's web
view, so the Node screen offers **Connect over USB** only where it's there
(`Radio.canUseUsb`). The app remembers which way it last connected, and
reconnects to a USB radio's port without asking again.

The plugin and Web Serial are behind the `BLE` and `SERIAL` tokens, so the
tests use `FakeBle`, a pretend companion radio that answers frames as a
real one does, and `FakeSerial`, a USB port with that same radio on it.

`src/app/node/`: `NodeLink` sends the node commands through the radio, one
at a time, and collects its answers (numbered parts put back in order) and
notices; `replies.ts` reads them. What it reads is pinned in
`../tests/fixtures/app_replies.json`, which `replies.spec.ts` and the bot's
`tests/test_app_replies.py` both check, so a reply can't change on one side
only.

`src/app/radio/presets.json` is a copy of the bot's MeshCore presets
(`mesh_contingency/radio_presets.py`) for the Radio tab, which
`tests/test_app.py` also keeps the same.

Radio links to **Open-source licenses** (`src/app/licenses/`): the
packages in the web build, read from the `3rdpartylicenses.txt` the
production build writes, and the Android libraries, listed by hand in
`ANDROID` there, with Capacitor's MIT license and an Apache 2.0 text that
angular.json copies in from `node_modules`. When an Android dependency
changes, check `./gradlew :app:dependencies --configuration
releaseRuntimeClasspath` (in `android/`) against that list.

Android asks only for Nearby devices (location on Android 11 and older,
which needed it to scan). Release builds have no internet permission; the
debug manifest (`android/app/src/debug/`) adds it for live reload.

## Working on it

```sh
npm ci                 # once, and after package-lock.json changes
npm start              # in a browser at http://127.0.0.1:4200 (in Chrome or Edge, a radio on USB works)
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

## The desktop app

The same app on Windows, Mac and Linux (roadmap item 18,
[`docs/plans/desktop-app.md`](../docs/plans/desktop-app.md)), in Electron:
`electron/main.cjs` opens a window on the web build (`dist/`, served as
`app://mesh/`, a secure origin as Web Bluetooth and Web Serial need).
Chromium leaves its device choosers and PIN prompt to the app, so
`electron/chooser.cjs` has its own: **Find my radio** looks for radios for
4 seconds and lists them; **Connect over USB** lists the serial ports; and
a radio that wants its Bluetooth PIN gets a box for it. On Linux, Web
Bluetooth needs Chromium's experimental platform features, which the app
turns on, and USB needs the user in the `dialout` (or `uucp`) group.

```sh
npm run desktop       # build, then open the desktop app
npm run desktop:run   # open the last build
```

The screens say "computer" there and "phone" on a phone (`DEVICE`, in
`src/app/device.ts`). Installers for each system come next (item 18, PR 3).

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
key is public, so it's only for test builds. Until there's a private
release key (roadmap item 16), each GitHub release attaches this debug APK
(`mesh-contingency-<version>-debug.apk`), for sideloading among people you
know. A build from before the shared key (2026-10-25) has to be
uninstalled once first.
