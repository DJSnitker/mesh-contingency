# Plan: the app on a computer (Windows, Mac and Linux)

Status: in progress: PR 1 (#95) merged; PR 2 (the Electron shell) open · Requested 2026-10-25

## Goal

The phone app (item 16, [mobile-app.md](mobile-app.md)) as a desktop app,
for a user whose MeshCore radio is beside their computer: the same screens
and commands, with the radio over **Bluetooth or a USB cable**. Released
for Windows, Mac and Linux alongside the Android APK.

## Decisions (2026-10-25)

- **Electron, not Capacitor or Tauri.** Capacitor builds for Android, iOS
  and the web only. Tauri uses each system's own web view, and Safari's
  (Mac) and WebKitGTK (Linux) have neither Web Bluetooth nor Web Serial, so
  the radio code would have to be rewritten in Rust. Electron is Chromium,
  which has both: the app's Angular build runs in it unchanged.
- **Bluetooth** goes through the same plugin
  (`@capacitor-community/bluetooth-le`), which uses Web Bluetooth when it
  isn't on a phone. Picking a radio already uses the system's chooser
  (`requestDevice`), which in Electron the app supplies itself
  (`select-bluetooth-device`).
- **USB** is Web Serial, with meshcore.js's serial framing
  (`UsbConnection`), offered wherever Web Serial is: the desktop app, and
  Chrome or Edge on a computer. Not on Android: its web view has no Web
  Serial, and a USB radio there would need a native plugin (not planned).
- **Unsigned builds first**, like the debug APK: Windows warns
  (SmartScreen) and macOS blocks the app until it's allowed in Settings.
  Signing (an Apple Developer account; a Windows certificate) is a later
  decision.

## PRs

1. **USB in the app** (#95) and this plan: `UsbConnection` over Web
   Serial, the Node screen's **Connect over USB**, remembering which way
   the radio was connected and reconnecting to its port without asking.
2. **The Electron shell** (`app/electron/`, this PR): a window on the
   app's build, the Bluetooth and serial pickers and the PIN box, the
   desktop's wording (computer, not phone), `npm run desktop` to run it.
   Electron 44.
3. **Builds:** CI makes the Windows installer, the Mac `.dmg` and the Linux
   AppImage, `.deb` and `.pacman` (Arch; decided 2026-10-25), with
   electron-builder on each system's runner, and
   each release attaches them, unsigned. The AppImage tried on Arch with
   and without FUSE 2 (`fuse2`). The licenses screen lists Electron's and
   Chromium's notices on a computer, in place of the Android libraries.
   Docs: the README, `app/README.md` and the wiki.
4. **Later, if wanted:** signing and notarizing; updates from inside the app.

## To check on real hardware

- **Linux Bluetooth:** Chromium's Web Bluetooth on Linux goes through BlueZ
  and has been behind a setting before; PR 2 tries it. USB on Linux needs
  the user in the `dialout` group (as the node's computer is).
- **Mac:** the Bluetooth permission prompt (the app's `Info.plist` usage
  text).
- **Windows:** a radio's USB serial driver (most MeshCore boards are
  driverless on Windows 10 and 11).
