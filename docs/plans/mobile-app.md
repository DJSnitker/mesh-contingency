# Plan: a phone app for users, over their own radio

Status: in progress: PRs 1–9 merged, the changes from the first phone test (#78–#81), a debug APK with each release since 0.9.0, and the wiki's App Guide; left, a signed release APK after a session with a second radio · Requested 2026-10-24 · Updated 2026-10-31 (App Guide)

## Goal

What a user does by typing commands to the node (join, check in, leave and
read messages, email out, ask for the weather) can be done from screens on
their phone. The phone talks to **their own** MeshCore companion radio over
Bluetooth, and the radio carries each request to the node as a direct
message, as it does today. No internet is needed between the phone and the
node: that's the point of a contingency mesh.

## Decisions (2026-10-24)

- **Capacitor + Angular**, one codebase for Android and iOS: native app
  packages with native Bluetooth (`@capacitor-community/bluetooth-le`), and
  the screens in Angular like the web console, reusing its design tokens,
  fonts, patterns and testing.
- **Android first.** It builds on this computer (Linux). iOS needs macOS to
  build and sign; it comes later, through a cloud Mac build (and an Apple
  developer account), from the same code.
- **The bot's replies stay as they are.** The app sends the usual commands
  and reads the usual text replies: no new protocol, no extra airtime. The
  reply formats the app reads become a tested contract (see
  [Reading replies](#reading-replies)).
- **First version:** connect and join; the mailbox; check-ins; email and
  weather; a chat screen for direct messages and channels; the radio's own
  settings. Each is its own PR.
- **No remote admin.** The app sends the node only user commands; admin
  work stays on the web console and over the radio. Its Radio tab changes
  the user's **own** radio, over Bluetooth, never the node's.
- **Named Mesh Contingency**, Android package id `com.meshcontingency`.

## How it fits together

```
phone app ── Bluetooth LE ──> user's companion radio ~~ mesh ~~> node's radio ── USB ──> bot
   │  (Nordic UART frames,         (direct messages,                              (unchanged:
   │   meshcore.js protocol)        ≤133 characters each)                          commands, checks,
   │                                                                                rate limits)
   └─ shows replies as screens; anything it can't read is shown as the text
```

**The bot doesn't change.** Every request is an ordinary direct message from
the user's radio, so the bot's identity check (the full key behind the
message's prefix), permissions, rate limits, confirmations and sealing all
apply exactly as they do to a typed command. The app is a nicer way to type.

**The radio protocol is meshcore.js** (`@liamcottle/meshcore.js`, MIT, the
MeshCore project's own JavaScript library). Its connections are small
subclasses of `Connection` that pass frames to and from the radio; the app
adds one, `CapacitorBleConnection`, on top of the Capacitor plugin, the same
shape as its `WebBleConnection`: the Nordic UART service
`6E400001-…`, writing to RX `…0002`, notifications from TX `…0003`. Writes
go through a queue (one GATT write at a time, which meshcore.js leaves as a
to-do). Only its own files are imported (`src/constants.js`,
`src/connection/connection.js`): its index also loads the Node.js-only serial
and TCP connections. `src/types/meshcore.d.ts` types the parts the app uses.

## The parts

### Connecting

- Scan for radios offering the MeshCore service; the user picks theirs. The
  phone's own pairing dialog asks for the radio's Bluetooth PIN.
- Android 12+ asks for Nearby devices (`BLUETOOTH_SCAN`, marked
  `neverForLocation`, and `BLUETOOTH_CONNECT`); older Android asks for
  location, which BLE scans needed then. Release builds have no internet
  permission; debug builds add it (`src/debug/`) for live reload. iOS later needs `NSBluetoothAlwaysUsageDescription`.
- The radio is remembered and reconnected to when the app opens. One phone
  app at a time can hold a radio's Bluetooth: if the official MeshCore app is
  connected, this one can't be, and says so.
- The app sets the radio's clock from the phone's on connect, as the bot
  does for its own radio, since messages are dated by it.

### Finding the node

- The user picks the node from their radio's contacts (it's there once the
  node's advert has been heard; a button sends an advert of their own so the
  node learns them too). The node's full key is kept; replies are matched to
  it, and nothing from any other contact is read as a reply.
- `whoami` tells whether they're a user yet; if not, **Join** sends `join`
  and explains that an admin approves it. The welcome the bot sends on
  approval is shown when it arrives.

### Sending a command and waiting for the answer

- One command at a time: the next waits until the last is answered or given
  up on, so replies can't be mixed up, and the bot's per-command rate limits
  aren't hit by the app itself.
- The app sends it again while it isn't acknowledged: three tries with the
  same timestamp, as MeshCore's own app does (the radio doesn't retry by
  itself). The screen shows sending, delivered or not delivered.
- `whoami` from someone who isn't a user gets `unrecognized user or
  function`, sent at most once every 5 minutes; so silence after it is read
  as "likely not a user", and Join is offered either way.
- Replies come as one or more direct messages from the node. A numbered reply
  (`(1/3) ...`) is put back in order and shown once every part is in, or
  after a while with what came. A reply can hold several messages each in
  numbered parts (an inbox of long messages), so parts are grouped by message,
  and a reply of several messages ends after a short quiet. Waits are generous (minutes over several
  hops) and say so.
- A message from the node that isn't a reply (a new-message notice, the
  join welcome, "An admin changed your email addresses") shows as a notice,
  even while a command waits; the fixtures pin those texts too. The welcome
  makes the app check again. (A phone notification for them comes later.)
- A refusal or failure from the bot (`limit reached`, `wrong passphrase`,
  `not sent, no internet at the node`) is shown as it says.

### Reading replies

Each command the app reads has a small parser in the app. If a reply doesn't
match, the app shows the text as it came: a reply the app can't read is
never lost or hidden.

So the bot can't change a reply and silently break the app, the formats are
pinned in one place both sides test: `tests/fixtures/app_replies.json`, a
list of cases (who sends what, the messages that come back, and what the
app reads from them; plus a long reply split into numbered parts). A Python test runs each command
against a fake state and checks the bot still says exactly `reply`; the app's
tests check its parser turns `reply` into `parsed`. Changing a reply then
means changing the fixture, which fails the app's tests until its parser
follows.

### Screens (first version)

- **Connect:** scan, pick the radio, its battery and name; reconnect.
- **Node:** pick the node; `whoami`; Join.
- **Mailbox:** the inbox (`inbox`, and `inbox <passphrase> [page]` with the
  passphrase asked each time, never stored), `msg` to a user, `clearinbox`
  and `clearinbox all`, `setpass` with its confirmation (folded away until
  opened).

The tabs, in order: Mailbox, Check-ins, Chat, Weather, Bible, Node, Radio;
Email opens from the foot of Mailbox (`/mailbox/email`), and the licenses
from the foot of Radio.
- **Check-ins:** `ok [status]` with quick choices ("ok", "need help", ...),
  each confirmed before it's sent,
  and `status [name]` (alone, your own). The roll call (`checkins`) is for
  admins, so it isn't in the app.
- **Email:** `qm`, `emailall` and `email`, each confirmed before it's sent
  (an email can't be taken back); `setqm` and `addgroup`/`cleargroup` to see
  and change the addresses.
- **Weather** (a tab): a card for each county the node watches, from the
  bot's `area` command (added for this after the first phone test): `area`
  lists them, `area <county>` sends one county's latest report from the
  bot's cache. Favorites are kept on the phone, shown first and loaded by
  themselves; with any, the rest wait under Show more, each loaded when
  asked, as each is a message over the mesh. Below, `wx <zip | county, ST>`
  for anywhere else.
- **Bible** (a tab): the verse of the day (`verse`), asked once a day and
  kept on the phone until the next, and `verse <reference>`.
- **Chat:** direct messages with any of the radio's contacts, and the
  radio's channels (Public, `#contingency-wx`, `#contingency-comm`, any
  other), to read and post, like the official MeshCore app. Three tabs:
  **Chat** (chats with people, newest first), **Channels** and **Contacts**
  (every companion, with a Find box once there are many, to start a chat).
  The radio's channels and contacts are read once per connection, the
  channels first, and shared with the Node and Radio screens; until the
  contacts are in, kept chats wait behind a spinner rather than show people
  by their keys. Delivered or not
  is shown for each direct message; a channel post's length is held to what
  fits. The history is kept on the phone (app storage, clearable), since the
  radio only holds messages until they're fetched. The node isn't one of the
  chats: its contact opens the Node screen, and what's sent to it (a
  passphrase with `inbox`) is never kept. The radio answers requests by
  kind, not by which request, so the app asks it one thing at a time: a chat
  message sent while a command waits can't take the command's answer.
- **Radio:** the user's own radio, over Bluetooth: its name, TX power,
  position and whether adverts share it, clock (set from the phone),
  battery, firmware, an advert (zero-hop or flood), and its frequency,
  bandwidth, SF and CR by MeshCore preset or by value, which asks first and
  says how to go back, as the console does: a radio on other settings than
  the mesh hears no one. Its contacts too: remove one, reset the path to one.
  The presets are a copy of the bot's (`app/src/app/radio/presets.json`,
  kept the same as `radio_presets.py` by `tests/test_app.py`). Like the bot,
  the app restarts the radio after a frequency change so it's surely in use,
  then offers to connect again. At its foot, a link to **Open-source
  licenses** (`/radio/licenses`): the packages in the app, from the
  production build's `3rdpartylicenses.txt`, and the Android libraries.

Every screen turns a spinner while it waits: connecting (the header too), a
command to the node, the radio's channels, contacts or settings, a Weather
card, a chat message being sent.

Styled like the web console: the same tokens and fonts (bundled, so nothing
is fetched from the internet), cards that fit a phone. On a tablet the
screens are a column down the middle (720 px at most), the tab bar too.

### Privacy

- The passphrase is typed for each `inbox` and `setpass` and never stored:
  it's held only while the Mailbox screen is open (for its next page), and
  the screens show `inbox` and `setpass` without it.
  It travels as any direct message does (encrypted between the two radios);
  the bot already never prints a private command's text.
- Opened messages are shown, not kept on the phone, apart from the current
  screen: the app's record of the last command drops an inbox's answer once
  the Mailbox screen has it.
- Nothing leaves the phone except through the radio.

## In the repo

`app/` beside `console/`: Angular 22, Capacitor 8, its Android project in
`app/android/` (committed, as Capacitor expects; build outputs ignored).
The console's stylesheet is listed in the app's build styles rather than
copied. Its icons are a copy (`src/app/icon.ts`) that a repo test keeps the
same: compiling the console's file from the app brings in a second Angular
from `console/node_modules`, which breaks at run time. `npm run demo` serves
the app in a browser on the tests' fake radio, with made-up contacts and
chats, to see the screens at any size. CI gets an **App** job (unit tests and the web
build) and an **Android build** job (`./gradlew assembleDebug`, keeping the
APK as an artifact). The Python package doesn't ship the app.

Building Android here needs the Android SDK (command-line tools, a platform
and build tools) and JDK 21, which the first PR's README section explains.
JDK 25 is installed now; the Android Gradle plugin is tested on 17 and 21,
so 21 goes beside it (sdkman is already here).

## PRs

1. **This plan** and its roadmap item. *Done: #65.*
2. **The app's skeleton:** `app/` with Angular and Capacitor, an Android build
   that installs and opens, the shared styles, the CI jobs, and the README's
   "Phone app" section (building, installing the APK). *Done: #66.*
3. **Bluetooth:** `CapacitorBleConnection`, the write queue, permissions and
   the Connect screen; tests against a fake plugin. *Done: #69.*
4. **Commands over the mesh:** send one, wait, put numbered replies back
   together, notices; the shared reply fixtures and both sides' tests; the
   Node screen (pick the node, `whoami`, Join). *Done: #72 (first merged
   into #69's branch as #70).*
5. **Mailbox.** *Done: #73.*
6. **Check-ins.** *Done: #74.*
7. **Email, weather and verse.** *Done: #75.*
8. **Chat:** direct messages and channels, and their history on the phone.
   *Done: #76.*
9. **Radio:** the radio's settings and contacts. *Done: #77.*
10. **Docs and a release:** the wiki's user guide, the changelog, a version
   number for the app, and a signed release APK. *The user guide is done:
   the wiki's App Guide (2026-10-31), with screenshots from `npm run demo`;
   the changelog and version came with 0.9.0–0.11.0. Left: the signed
   release APK.*

Then the first phone test (below) brought #78–#81.

iOS after that: a cloud macOS build (GitHub Actions' macOS runners), with
TestFlight once there's an Apple developer account.

## First phone test (2026-10-25)

On the user's Pixel 9 Pro, with the CI debug APK, then builds installed over
USB; later also on a Lenovo tablet (TB336FU, landscape). The app connected
to the user's radio once the official MeshCore app had let go of it (a radio
takes one Bluetooth connection at a time). What it brought:

- **#78:** the logo as the launcher icon; the tabs as they are now; the
  passphrase box folded away; the Weather tab's county cards, from a new
  public bot command `area` (the live node has `area = { permission =
  "public" }`); the Bible tab; one shared debug signing key in the repo,
  so each build installs over the last and keeps the app's data.
- **#79:** the bot no longer warns at startup that `area` has no counties
  (it checked before the alert watcher had read them).
- **#80:** Send stayed disabled in a chat opened from a kept chat's key
  prefix, before the contacts had loaded; fixed. Then Chat's three tabs, the
  contacts read once per connection, the spinners, the tablet layout, the
  Radio tab no longer running off a narrow phone's edge, and `npm run demo`.
- **#81:** the Open-source licenses page, linked from Radio.

Reading the contacts took only a few seconds on the real radio.

Still to check with a second radio and another user: a direct message
delivered both ways, a channel post heard, every screen's command to the
node answered over the mesh, and the Radio tab's changes on a real radio,
most of all **Share it in adverts** (a hand-written `SetOtherParams` frame)
and reading the radio's location policy.

## Testing

Unit tests run anywhere (vitest, a fake radio connection like the console's
`FakeApi`). The real test needs an Android phone and a second companion radio
with Bluetooth, which is what field testing (roadmap item 9) is waiting for:
until those radios arrive, each PR is checked on the emulator against the
fake connection, and the Bluetooth parts wait for the hardware. Since
2026-10-25 the app also runs on the user's phone with their own radio
(see [First phone test](#first-phone-test-2026-10-25)), which covers
connecting and the radio's own requests, but not a second user.

## Open questions

- Distribution: sideloaded APKs to start; Google Play (a one-time developer
  fee) when it's worth it.
- The release signing key (PR 10): where it's kept and who holds it. The
  debug key is in the repo on purpose; a release key must not be.
