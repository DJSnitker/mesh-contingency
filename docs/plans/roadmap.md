# Roadmap: after the user-management plan

Status: every item but field testing and the phone app done, 0.8.2 released; field testing paused · Written 2026-10-21 · Updated 2026-10-24 (phone app planned)

Every earlier plan is built (`security-and-live-users.md`,
`private-mailbox.md`, `user-management-and-robustness.md`; PRs #1–#16), and
since then names come from the radios (#18), `quickim` is `qm` (#20) and names
with spaces go in parentheses (#23). This
lists what to do next, in the recommended order. Each item is its own branch
and PR, with tests, README and wiki updates, like the earlier work.

| # | What | Kind | Size | Status |
|---|---|---|---|---|
| 1 | Release 0.3.0 with a changelog | release | small | done (v0.3.0) |
| 2 | Automatic weather alerts | feature | medium | done (channel only) |
| 2a | Release 0.4.0 | release | small | done (v0.4.0) |
| 3 | #contingency-comm channel at startup | feature | small | done |
| 4 | Roll call of check-ins | feature | small | done |
| 5 | Report email failures (no queue) | feature | small | done |
| 5a | Release 0.5.0 | release | small | done (v0.5.0) |
| 6 | Alerts to admins about the node itself | feature | medium | done |
| 7 | Backups of the bot's data | feature | small | done |
| 7a | Release 0.6.0 | release | small | done (v0.6.0) |
| 8 | Does the radio restart when the bot connects? | check, docs | small | done: no |
| 9 | Field testing on real radios | testing, no code | small | paused: waiting on more radios |
| 10 | Web console on the node (Angular) | feature | large | done: [web-console.md](web-console.md) |
| 10a | Release 0.7.0 | release | small | done (v0.7.0) |
| 11 | Open the console with one command | feature | small | done |
| 12 | Manage the radio from the console: contacts and settings | feature | large | done (#57, #58) |
| 13 | The weather now on the dashboard | feature | medium | done |
| 13a | Release 0.8.0 | release | small | done (v0.8.0) |
| 14 | `wx` takes a county as well as a zipcode | feature | small | done (#60, v0.8.1) |
| 15 | Admins set a user's email addresses (`setemail`, console Edit emails) | feature | small | done (#62, v0.8.2) |
| 16 | Phone app for users, over their own radio's Bluetooth (Android first) | feature | large | planned: [mobile-app.md](mobile-app.md) |

Recommended order: everything but field testing is done and released (0.8.2). Next, the phone app (16), PR by PR; its Bluetooth checks, like field testing (9), wait for the radios.
Field testing (9) waits for more radio equipment; it was started 2026-10-21 and its results so far are kept below.

## Resume here (next session)

Where things stood on 2026-10-23:

- **Merged and released:** everything but field testing. Since 0.7.0: #53
  (the demo console), #54 (this backlog), #55 (item 11), #56 (item 13), #57
  (12a: contacts, channels and their messages) and #58 (12b: radio
  settings), released as **0.8.0** (#59, tag `v0.8.0`). The wiki's Admin
  Guide has "Use the web console" and "Change the radio's settings". Then
  #60 (`wx Taylor, TX`: a county as well as a zipcode), released as
  **0.8.1** (#61, tag `v0.8.1`); the wiki's Commands page covers it. Then
  #62 (`setemail` and the console's Edit emails), released as **0.8.2** (this
  PR, tag `v0.8.2`); the wiki's Commands page and Admin Guide cover it.
- **The node** runs `main` with `comm`, `checkins`, `backup`, `contact` and
  `radio` as admin in its `config.toml`; `#contingency-wx` is channel slot 1
  and `#contingency-comm` slot 2. Its console is on (port 8737); the link is
  in `console.url`, new at each start (`mesh-contingency-console` opens it).
  After a pull that changes `console/`: `npm ci && npm run build` there, then
  restart the bot. The bot sets the radio's clock at each start (a reboot
  resets it).
- **Item 8 answered: no, so far.** Opening the radio's USB port didn't restart
  it (checked 2026-10-22; details in item 8). **Monitor:** a `Node problem:
  the radio restarted ...` right after a bot restart is the pattern to note.

Steps, in order:

1. If the computer was restarted, check the service came back:
   `systemctl --user status mesh-contingency`; the journal should show
   `comm: #contingency-comm is channel slot 2.` After the next reboot, check
   #41 for real: admins get `Node restarted: the computer started ...`, not
   `Node problem: the radio restarted ...`, and `health` doesn't say
   `last check failed`.
2. After Wednesday 2026-10-28, 17:00: check the weekly alert test arrived on
   a radio, and record it in item 9.
3. The web console checks still to do on the node (item 9, "Web console on
   the node"): a channel message heard, a real **Remove**, **Post alert
   test**, and TX power, position and `radio freq`.
4. The node backs up daily to `~/MeshContingencyBackups` for now; move
   `[backup] to` to a separate disk (USB stick, second drive) when there is
   one.
5. Use the web console day to day, and note anything that would make it
   better; access from other devices is out of scope until it has real
   logins and HTTPS (see [web-console.md](web-console.md)).
6. The phone app (item 16, `com.meshcontingency`): next is
   PR 2 of [mobile-app.md](mobile-app.md), the skeleton.

Paused: item 9, field testing, until more radios arrive.

---

## 1. Release 0.3.0 with a changelog (done)

*Done 2026-10-21:* version 0.3.0, `CHANGELOG.md` with upgrade steps from
0.2.0, tag `v0.3.0` and a GitHub release with the changelog entry.

`pyproject.toml` said `0.2.0` although PRs #1–#24 added a lot. Decided: a tag
and release notes, no release workflow building a wheel for now.

Field testing (item 9) now comes after this release, while more radios
arrive; anything it finds goes into a 0.3.x release. Say so in the release
notes: tested so far on one radio.

- Bump `version` to `0.3.0`.
- New `CHANGELOG.md` (Keep a Changelog style): an entry for 0.3.0 summarising
  sealed mailboxes, user management, limits, adverts and `contacts`,
  names taken from the radios (with `( )` around names with spaces, and
  `rename` removed), `quickim` renamed `qm` (and `setquickim` `setqm`), and
  the profanity filter, the systemd service, `health`,
  `history` and backups, the hardening, the wiki and logo. Note what existing
  nodes must do on upgrade: add the `[commands]` lines for new commands
  (`health`, `history`, `contacts`, the user commands), delete the
  `rename` line (it only warns), rename `quickim` and `setquickim` to `qm`
  and `setqm` under `[commands]` (until then the bot warns and uses the old
  lines; users' addresses in `users.toml` convert themselves), `chmod 600` on
  `~/.mailrc`, re-run `pip install -e .`.
- Tag `v0.3.0` and publish a GitHub release with the changelog entry
  (`gh release create v0.3.0 --notes-file ...`).
- Decide: does CI need a release workflow (build and attach the wheel), or is
  a tag enough? Suggest: a tag and notes only for now.

## 2. Automatic weather alerts (done)

*Done 2026-10-21:* `[alerts]` in `config.toml` (`counties`, `every_minutes`,
`channel`), `mesh_contingency/alerts.py` with the shared channel helpers and
`AlertWatcher`, `alerts.json`, "auto" in `history`, and a line in `health`.
Changed from the design above:
- It watches **counties** (`"Taylor, TX"`), not zipcodes, which were too
  fine-grained: a county is what the NWS issues warnings for, and every
  zipcode in one gets the same alerts. Posts are named by county.
- Each county's NWS code is looked up once (kept in `alerts.json`; the admin
  command `alertmap` looks them up again), and each round is one
  `/alerts/active?zone=TXC441,...` request for every county. The NWS includes
  alerts issued for forecast zones in those counties; each alert's FIPS
  (`SAME`) codes say which watched county it belongs to.
- With the NWS alerts automatic, `alert <message>` now posts an admin's own
  message to the alert channel instead of a zipcode's alerts. (Item 3 is
  still about direct messages to every user.)
Decided: **channel only**; DMs for Warnings stay a possible follow-up.

Today an admin has to send `alert <zipcode>`. Instead, the bot watches a list
of zipcodes and posts each **new** National Weather Service alert to the
alert channel by itself.

- **Config:**
  ```toml
  [alerts]
  zipcodes = ["79601", "79602"]   # watched; empty (the default) turns it off
  every_minutes = 10              # how often to check api.weather.gov
  channel = "#contingency-wx"     # defaults to [commands.alert] channel
  ```
- **Design:**
  - A background task like `advert_on_schedule`: every `every_minutes`,
    `weather.fetch_alerts(zip)` for each zipcode (in a thread, as `alert`
    does).
  - Posts only alerts not posted before, by the NWS alert `id`. Keep posted
    ids with their expiry in `alerts.json` (next to `config.toml`,
    git-ignored), so a restart doesn't repost, and drop expired ones.
  - Several zipcodes often share one alert: post it once, naming the first
    zipcode (or the area description).
  - Reuse `format_alerts` and the channel-slot logic from
    `commands/alert.py` (move them somewhere shared, e.g. `alerts.py`).
  - Network errors: log once, retry next round; never crash the bot.
  - Record each automatic post in `history` as by "auto".
- **Optional, decide first:** also DM every user (or only those who opt in
  with a new `alerts on/off` user command) for Warnings (not Watches or
  Advisories), or only post to the channel? Suggest: channel only first;
  DMs as a follow-up, since they cost airtime per user.
- **Tests:** new alert posted once; same alert next round not reposted;
  restart with `alerts.json` doesn't repost; expired ids dropped; shared
  alert across zipcodes posted once; fetch failure logged and retried;
  disabled when `zipcodes` is empty.
- **Docs:** README `[alerts]`, wiki Admin Guide "Warn people about the
  weather", `health` could show "auto alerts: 2 zip(s), last check 3m ago".

## 3. #contingency-comm channel at startup (done)

*Done 2026-10-21:* `CommCommand` joins `#contingency-comm` at bot startup and
stays joined. Admins post to it with `comm <message>` (admin, like `alert`);
anyone can post from their own radio. The channel appears automatically in
radio slots alongside `#contingency-wx` (the alert channel).

Reason for change: a dedicated communication channel is simpler and more mesh-friendly
than broadcasting direct messages to every user (which would cost airtime per user).
Admins can post important updates to the channel for all to see at once.

## 4. Roll call of check-ins (done)

*Done 2026-10-21:* `checkins [page]` (admin) lists all users and their
check-in status, with pagination to keep mesh messages within size limits.

- Shows who's checked in (with timestamp) and who's missing.
- Paged: 5 per-page, with hint message `"Page 1/3. Use 'checkins page <n>' to see other pages."`.
- Returns structured data for future web interface.
- Useful during and after events to see who's accounted for at a glance.
- Does *not* show the full check-in message text; use `status <name>` for details.

## 5. Report email failures (done)

*Decided 2026-10-21: no outbox.* Emails aren't queued to retry; every failure
to send is reported instead.

- `mail` hands each message to msmtp, which sends to Gmail straight away;
  nothing on the node queues mail, so a failure shows up at once (s-nail
  exits 4, "message not sent").
- The sender's reply gives the cause, from msmtp's wording:
  `qm: not sent, no internet at the node; try again later`; also login
  refused, address refused, timed out, not set up, other. Never `mail`'s own
  output, which can hold the node's Gmail address.
- The full reason goes to the console/journal; `health` shows
  `last email failed 5m ago: <cause>`; failures still count as errors and
  not toward the email caps.
- `mail` runs with `DEAD=/dev/null`, so s-nail no longer leaves the unsent
  message in `~/dead.letter`, unsealed.
- Telling admins about repeated email failures belongs to item 6.

## 6. Alerts to admins about the node itself (done)

*Built 2026-10-22* as the **node watch**, `[watch]` in `config.toml`, on by
default (`mesh_contingency/watch.py`).

- Every `every_minutes` (5) it reads the radio's battery and uptime and DMs
  every admin `Node problem: ...` when a problem starts and `Node ok again:
  ...` when it's over:
  - battery below `battery_volts` (3.5 V), ok again 0.1 V above it;
  - `undelivered_in_row` (5) messages in a row not acknowledged, until one is;
  - email failing for a reason at the node (item 5; a refused address
    doesn't count), until one is sent;
  - `errors` (3) commands failed or timed out within 30 minutes;
  - `users.toml` not reloadable, until it is (the old immediate notice
    folded in; the watch is woken straight away for it).
- A radio restart (uptime going backwards, item 8) is announced once, with
  no "ok again"; the radio's start time is kept in `watch.json`, so one that
  also restarted the bot (USB unplugged) is caught.
- At most one announcement per problem per hour, each followed by one "ok
  again"; what's been announced is in `watch.json`, so a bot restart doesn't
  repeat an ongoing problem.
- `health` shows `watch: no problems` or the current ones.
- `enabled = false` turns it off; the users-file notice then goes out
  immediately as before.

## 7. Backups of the bot's data (done)

*Built 2026-10-22,* in the bot rather than as a systemd timer, so the same
code makes the scheduled backup and the admins' `backup` command
(`mesh_contingency/backup.py`).

- `[backup]`: `to` (default `~/MeshContingencyBackups`, the user's choice
  for now), `every_hours` (24; 0 for only the command), `keep` (7).
- Each backup is a new folder named for the time in `to`: `config.toml`, the
  users file, the JSON state files and the users file's `backups/`, with
  their permissions; folders made 0700. Only the folders it made are pruned.
- `backup` (admin) makes one now and says where; `history` records each
  (scheduled ones as "auto"); `health` shows `last backup 3h ago`.
- A failure (disk not mounted, full) is logged with the reason, retried in an
  hour, and becomes a node-watch problem until a backup works.
- At startup the bot notes when `to` is on the same disk as the data; the
  README and wiki say to put it on a separate disk.

## 8. Does the radio restart when the bot connects? (done: no)

*Checked 2026-10-22 on the node's Heltec V3 (firmware v1.18.0):* opening its
USB serial port does **not** restart it.

- With the service stopped, a script opened the port, read the radio's
  uptime, closed it, and did the same 20 seconds later: 33445 s, then
  33465 s.
- The journal agrees: on 2026-10-20 `health` said `up 4m` but `radio up 13m`,
  and several service restarts on 2026-10-21/22 didn't reset `radio up`. The
  one `radio up 0m` (2026-10-21 23:06) followed the USB cable being unplugged
  (kernel: `usb 3-1: USB disconnect`), which also made the bot exit.
- So `radio up` shorter than the bot's `up` means a real radio restart (power,
  USB, crash); item 6 can alert on uptime going backwards without excusing
  bot restarts. Documented in the wiki (Commands: `health`; Admin Guide:
  Check the node's health).
- **To monitor:** on 2026-10-22 at 13:11:56 the bot was restarted (after
  merging #37) and the radio itself started at 13:11:58; the first connect
  failed, systemd's retry 30 s later worked, and the node watch's restart
  notice was delivered. No USB disconnect in the kernel log, the button
  wasn't touched; a system update had finished at 13:02. Restarts at 12:49
  and 13:04 didn't do it. If it happens again after a bot restart, suspect
  the USB chip's control lines resetting the ESP32 when the port is opened,
  and hold them steady on open.

## 9. Field testing on real radios

**Paused** until more radio equipment arrives: most checks need a second
radio (another user, a joining stranger, a renamed radio).

Everything below has passed unit tests; each check is marked once it has
been tried end to end on radios. Watch the journal (`journalctl --user -u
mesh-contingency -f`) during each; anything that fails becomes a bug fix
in a 0.3.x release.

### Results so far

**2026-10-21, from one radio (the admin's, also a user), journal checked:**

- *Passed:* `setpass`; `msg (<own radio name>) ...` with the name in
  parentheses was accepted and sealed (`sealed message for ...` in the log);
  plain `inbox` said how many were waiting without showing them;
  `inbox <passphrase>` showed the text; `inbox <wrong passphrase>` was refused;
  `clearinbox` and `clearinbox all` deleted them. Every reply was delivered,
  and the log showed only `(private)` for commands carrying message text or a
  passphrase.
- *Noticed:* messages sealed under an earlier passphrase couldn't be opened
  (as designed); the fix was `clearinbox all` and a new `setpass`. Typing
  `resetpassword` got `unrecognized user or function`; the admin command is
  `resetpass <name or key>`. Possible follow-up: suggest the nearest command
  to users and admins (not to strangers).
- *Still to do in these two checks:* a message from **another** user's radio;
  `mailbox.json` inspected while a sealed message is waiting (it was empty
  after `clearinbox`); `msg` with a plain name with spaces, `whois` and
  `status` with parentheses.

**2026-10-22, 11:47–12:02, the admin's radio and a second user's radio,
journal checked:**

- *Passed:* `comm hello contingents` posted to `#contingency-comm` (slot 2)
  and replied; `checkins` listed both users as missing (before any
  check-in). **Email failure for real:** `qm howdy` with no DNS got the "not sent,
  no internet" reply, and the node watch DMed the admin `Node problem: email
  failing: no internet at the node` 88 s later (delivered). **Lost radio:**
  USB unplugged 11:52–11:59: `Lost the radio (reconnect_failed); stopping.`,
  `No serial device found` every 30 s (15 tries; systemd kept going), then
  connected 24 s after the replug, both channels in place. The second radio's `ok`, sent
  while the bot was down, was handled right after. `radio up 12h 55m`
  showed the Heltec ran on its battery while unplugged, so the watch rightly
  sent no restart notice. `qm` then sent an email; `health` came in 4 parts
  (120/133/114/90 chars, all delivered) with `last backup` and `watch: no
  problems`; `backup` saved 13 files.
- *Bug found and fixed (PR after #34):* right after the restart the watch
  sent `Node ok again: an email was sent` though none had been: the problem
  was remembered in `watch.json` but its evidence was only in memory. "Ok
  again" now needs evidence (an email sent, a message delivered, a backup
  made after the announcement; 30 minutes for command errors).
- *Added from it:* the bot was down 7 minutes and nobody was told, so a lost
  radio is now recorded and announced once it's back: `Node problem: the
  radio was disconnected for 7m (reconnect_failed); back now`.
- *Noticed:* 2 of the second radio's 3 replies weren't acknowledged (radio
  link, not the bot). It tried `status` with the node's own name; `status`
  looks up users, so it said "no status for ..."
- *Still to do:* the weekly alert test (Wednesday 2026-10-28, 17:00)
  arriving on a radio. (Reboot: done 2026-10-22, below.)

**2026-10-22, 12:50–13:12, after #36 and #37:**

- *Passed:* **disconnect notice for real:** USB unplugged 12:50:33–12:54:35;
  once back, one DM, `Node problem: the radio was disconnected for 4m
  (reconnect_failed); back now`, delivered; not repeated on later restarts.
  **Suggestions:** `hlep` got `unknown command hlep; did you mean help?
  help lists yours`, delivered. **Radio restart notice:** sent and
  delivered when the radio restarted at 13:11:58 (not by power loss; see
  item 8, to monitor).

**2026-10-22, 15:56–15:58, reboot without logging in, admin's radio:**

- *Passed:* the service came back on its own at boot. The first connect
  failed (`Could not connect to MeshCore device`: the radio was still
  starting after USB power came back) and systemd's retry 30 s later
  connected. `health` and `roster` from the admin's radio were answered, all
  replies delivered; battery 4.17–4.21 V.
- *Found:* the watch sent `Node problem: the radio restarted just now
  (power, USB or a crash)`: true (`radio up 0m`; the reboot cut USB power),
  but alarming for a planned reboot. And the first NWS check ran before the
  network was up (`Temporary failure in name resolution`), so `health` said
  `last check failed` until the next round 10 minutes later.
- *Fixed in #41:* on Linux the watch reads when the computer started, and a
  radio that started with it gets `Node restarted: the computer started 1m
  ago, and the radio with it` instead; the first alert check waits up to 2
  minutes for api.weather.gov to resolve. Not yet seen on a real reboot.

### Checks

- **Service, reboot** (passed 2026-10-22; see above): reboot without logging
  in; `help` from another radio gets an answer. Since #41, expect one
  `Node restarted: ...` DM, not `Node problem: the radio restarted ...`.
- **Service, lost radio** (passed 2026-10-22, twice; see above): unplug the
  radio while the bot runs, wait, plug it back in. Expect `Lost the radio
  (...); stopping.`, `No serial device found` every 30 s while unplugged,
  `Connected to ...` about 30 s after the replug, then one DM to admins:
  `Node problem: the radio was disconnected for ...; back now`.
- **Sealed messages** (mostly passed 2026-10-21; see above):
  `setpass <12-16 chars>`; another user sends `msg`;
  `inbox` shows only who and when; `inbox <passphrase>` shows the text;
  `inbox <wrong>` is refused; `clearinbox`. Check `mailbox.json` holds
  `sealed`, not the text.
- **Joining (names are radios' names, PR #18):** `join` from a radio named
  with a space (e.g. `Sam T-Deck`) asks under exactly that name; `join` from a
  radio with a profane name, or one with parentheses, is refused;
  `approve (Sam T-Deck)` works.
- **Names with spaces** (`msg (name)` passed 2026-10-21):
  `msg sam t-deck hi` and `msg (Sam T-Deck) hi` both
  reach the user; `whois (Sam T-Deck)` shows them; `status sam` finds their
  check-in.
- **Renamed radio:** rename a user's radio in the app, send the node any
  command from it; the log shows `... is now <new name>, the radio's name`,
  `users.toml` has the new name, and `history` lists it as by `radio`.
- **Quick message (renamed in PR #20):** `setqm` alone shows the address;
  `setqm <address>` changes it; `qm <message>` arrives by email with the
  sender's radio name in the subject; `quickim` from a user now gets
  `unknown command quickim; did you mean qm? help lists yours` (from a
  stranger, `unrecognized user or function`).
- **Admin tools:** `approve`, then `history` lists it; `backups/` holds the
  previous `users.toml`; `health` reflects the new user; `remove` asks before
  acting.
- **Limits:** a burst of `wx` from a public sender gets one "limit reached"
  reply, then silence.
- **Web console on the node** (tried 2026-10-23: the pages, `contact path`,
  `reload`, `alertmap`, the radio's settings, `radio clock`, a rename and
  back, and `radio reboot`; see item 12b): still to do, a message heard on a
  channel showing on the Radio page; **Remove** of a real contact (it asks
  first; one `auto_add` takes comes back when it adverts); **Post alert
  test** arriving on a radio; and `radio power`, `radio position` and `radio
  freq` (the last on a spare radio if one arrives: the confirm says what to
  send to go back).

## 11. Open the console with one command (done)

*Built 2026-10-23* as `mesh-contingency-console` (`mesh_contingency/web/launch.py`), a
second command rather than a flag, since it neither connects to the radio nor
runs for long. Decided while building it:

- **It opens the link itself,** as `console.url` has it, with Python's
  `webbrowser`. A first version gave the browser a `file://` page that went
  on to the link, to keep the key out of `ps`; but a browser sent on from
  another page doesn't send the `SameSite=Strict` cookie along the redirect
  after the key, so it landed on *Open the console's link*. The cost: other
  accounts on this computer can see the key in `ps` (for as long as the
  browser runs, if this started it), though not read `console.url`. Fine
  for a node with one account; if that changes, see the first version, with
  the bot answering a cross-site key with a page that goes on from its own
  address.
- **No desktop launcher yet:** its messages (bot not running...) would have
  nowhere to show. Later, if wanted, with a notification for those.

The plan, as written before:

*Asked 2026-10-23.* Today the link has to be copied out of `console.url` or
the journal, and it changes at every restart. Instead, one command on the
node's computer opens it in the browser:

```sh
mesh-contingency-console          # or: mesh-contingency --open-console
```

- **What it does:** reads `console.url` beside `config.toml` (`-c` as the
  bot takes it), checks the bot answers on that address, and opens the link
  with Python's `webbrowser` (which uses `xdg-open` on Linux). Messages for
  the usual mistakes: the console is off (`[console] enabled = false`), the
  bot isn't running (no `console.url`, or nothing answers), the app isn't
  built.
- **The bot itself can't open it:** as a systemd service it has no desktop,
  so this is a separate command the admin runs, a second entry point in
  `[project.scripts]` (decide: a new command, or a flag on the existing one).
- **Keep the key off the command line:** a browser started with the link as
  an argument shows the key in `ps` to anyone on the computer. Instead, write
  a small page (mode 600, in a private temp folder) that sends the browser
  on to the link, and open that `file://` page; remove it after a few
  seconds.
- **Maybe also:** a desktop launcher (`deploy/mesh-contingency-console.desktop`)
  so it's an icon in the applications menu.
- **Docs:** README Web console, the wiki Admin Guide ("Open it" and the
  *Open the console's link* troubleshooting row), changelog.

## 12. Manage the radio from the console: contacts and settings (done)

*Asked 2026-10-23.* The Radio page has Advert, Flood advert and Back up now.
Add what an admin otherwise does with the MeshCore app on a phone plugged
into the radio: its contacts, and its settings. Split in two PRs, contacts
first.

**12a. Contacts.** The radio holds a fixed number (the dashboard's
`contacts 41/350`), and with `[contacts] auto_add` it fills up.

- A list on the Radio page: name, kind (chat, repeater, room), key prefix,
  last advert, the path (direct or flood, and hops), and which are users or
  admins.
- **Remove** a contact (`remove_contact`), with confirm; it says if the
  contact is a user, since they can't be answered until they advert again.
  **Reset path** (`reset_path`) for a contact whose messages stopped
  arriving.
- Maybe: remove all not heard from in N days; **Add** from a shared contact
  URI (`import_contact`).
- **Done (12a):** a new admin command, `contact remove|path <name or key>`,
  so the radio and the console do the same thing, with `remove`'s confirm
  (asking about another contact starts over). A contact is found by its
  whole name, then 4+ hex digits of its key, then the start of its name;
  several matches ask for more of the key. The library only ever adds to its
  copy of the contacts, so `remove` drops it there too. `/api/contacts` gives
  the list (path length from `out_path_len`, -1 meaning none; `last_advert`
  by the radio's clock) and the radio's `max_contacts`. On the Radio page the
  list is there even with `contact` off, without the buttons. The badge,
  danger-button and filter styles moved to `styles.scss` to be shared. Not
  done: removing in bulk, and Add.
- **Also (asked 2026-10-23): the radio's channels,** read-only, on the Radio
  page (`/api/channels`): slot, name, kind (public, hashtag, private) and
  what the bot posts there. `read_channels` in alerts.py, now also used by
  `channel_slot`. No keys: one would let anyone read a private channel.
  Changing channels stays with the MeshCore app for now (could join 12b).
- **Also (asked 2026-10-23): a channel's messages,** in memory only (the
  user's choice: nothing of other people's channel traffic on disk). The
  bot subscribes to CHANNEL_MSG_RECV only while the console is on
  (channel_log.py, the last 200 a slot); `post()` adds the bot's own posts,
  which don't come back from the radio. Read every 10 s while a channel is
  open and its tab shows. Contacts and channels became tabs, and the menu
  the Dashboard, a line, then A–Z.

**12b. Radio settings.** Shown first, then changeable one at a time:

- **Read:** name, frequency, bandwidth, spreading factor, coding rate, TX
  power, position (`self_info`), clock (`get_time`) and firmware
  (`send_device_query`).
- **Change:** name (`set_name`; users see the new one after the next
  advert), TX power (`set_tx_power`, within the radio's maximum), position
  (`set_coords`, also the location for item 13), set the clock from the
  computer (`set_time`), reboot the radio (`reboot`; the bot already
  reconnects).
- **Frequency, bandwidth, SF and CR (`set_radio`) are the dangerous ones:**
  a mismatch with the rest of the mesh cuts the node off, and the console
  can't fix it over the radio. Offer them last, with the regional presets,
  a confirm that says this, and maybe only after typing the node's name.
- **Settings `config.toml` owns stay there:** `auto_add` (manual add
  contacts) and the advert schedule are set from `config.toml` at each
  start, so the console shows them read-only; it doesn't edit `config.toml`
  (decided for item 10).

**How (both):** as for item 10, every button runs a command, so the radio and
the console share the same rules, `history` and confirm (`asks`): e.g. an
admin `contact` command (`contact remove <name or key>`,
`contact path <name or key>`) and an admin `radio` command (`radio`,
`radio name ...`, `radio power ...`, `radio clock`, `radio reboot`, `radio
freq ...`). Decide, for each: offered over the mesh too, or console only
(`radio freq` sent over the mesh could cut off the admin who sent it). The
API adds the radio's settings to an `/api/radio` read. Tests with
`FakeMeshCore` (it needs the new calls); then try each on the node's Heltec
V3, the frequency change last and on a spare radio if one arrives.

- **Done (12b):** decided 2026-10-23: **everything console only** (over the
  mesh `radio` only shows the settings), and the frequency change included.
  The console reaches the radio over USB, so a wrong frequency cuts off the
  mesh, not the console: the confirm says what to send to go back. The
  presets are MeshCore's (radio_presets.py, copied from
  api.meshcore.nz/api/v1/config on 2026-10-23; a preset's path hash size is
  left alone). `radio reboot` and `radio freq` ask first, then call
  `state.restart`: the bot stops 2 s later with exit 1 for systemd to start
  it again, and the radio dropping meanwhile isn't a lost radio. The
  Settings tab is first on the Radio page; the frequency button waits for
  the node's name. `/api/radio` never includes `ble_pin`. Changing channels
  still stays with the MeshCore app.
- **Tried on the node's Heltec V3 (2026-10-23):** the read (USA preset, 22/22
  dBm, no position, firmware v1.18.0); `radio clock` (it was 3h 26m behind);
  rename and back; `radio reboot` twice. The bot stopped 2 s after, and came
  back 67 s after the reboot: both times its first reconnect, 30 s on,
  failed ("Could not connect"), as after #41's computer reboot, and the next
  worked. The first reboot DM'd the admin "Node problem: the radio
  restarted", so `radio` now tells the watch first (`rebooting` in
  watch.json) and the next run only logs it; the second reboot showed that.
  **A reboot resets the radio's clock** (4h behind after), so the bot now
  sets it at each start when it's 5 s or more off (asked 2026-10-23). Not
  tried: TX power, position, `radio freq`.

## 13. The weather now on the dashboard (done)

*Built 2026-10-23* as **Area Weather**, a page of its own after the Dashboard
(`mesh_contingency/area_weather.py`, `/api/weather`, `area-weather.ts`).
Decided while building it:

- **Its own page, not a section of the dashboard** (the admin's choice,
  after seeing it there): 19 cards made the dashboard long, and the live
  log ended up far below them. The dashboard has an **Alerts** row instead,
  above Watch: the alerts out now, each with its counties, orange while
  there are any, linking to Area Weather (also the admin's ask; before, the
  dashboard said only that the watcher ran).

- **A card for each county in `[alerts]`,** not one place (the admin's
  choice): no new setting, and the counties are the area the node serves.
  Each card has the latest observation, the next three forecast periods
  (with the chance of rain), and that county's alerts.
- **Where to ask about a county:** the middle of its NWS outline, then
  `/points` there for the town named nearest, the forecast's address and the
  three nearest stations. Looked up once and kept in `area_weather.json`
  (looked up again if the county's code changes). Each round is then about
  two requests a county: on the node, 19 counties took 49 s the first time
  and 14 s after. Neighbouring counties often share a station (five read
  Abilene's airport).
- **Alerts come from the alert watcher,** which now keeps each county's
  active alerts (`current`) at each check, so there's no second request. An
  alert for a forecast zone that names no watched county goes under the
  first, as when it's posted.
- **Only with the console on** (and counties in `[alerts]`): nothing else
  reads it. Every 15 min, or after 1 min when a round got nothing at all
  (no network yet at boot). A failure keeps the last report; the card says
  how old it is and why.
- **The `wx` command is unchanged;** it still takes a ZIP code.

The plan, as written before:

*Asked 2026-10-23.* The dashboard shows the node; add the weather where it
is, whether or not there's an alert: what `wx` gives over the radio, but
always there.

- **What:** current conditions from the nearest NWS station (temperature,
  wind, humidity, the text such as *Partly Cloudy*, and when observed), the
  chance of rain in the next hours, the next few forecast periods (*Tonight:
  Low 48, clear*), and the active alerts for the counties `[alerts]` watches
  (from the alert watcher, which already asks every 10 min, not a second
  request).
- **Where it is:** decide between the radio's own position (`adv_lat`,
  `adv_lon`, if set: see 12b) and a ZIP code or lat/lon in `config.toml`
  (e.g. `[console] weather = "79601"`); no location, no panel.
- **When:** the bot fetches it every 10–15 min and keeps the last one, so
  opening the dashboard doesn't call `api.weather.gov` each time, and the
  page polls `/api/weather` as it does `/api/overview`.
- **When the internet is down** (when the node matters most): the panel
  says so and keeps the last report, with its time; the rest of the
  dashboard is unaffected. Uses `weather.py` (`fetch_weather`), adding the
  forecast call.
- **Tests:** the API with a fake fetch (fine, failing, never fetched), and
  the panel in Vitest; then on the node, and with the network unplugged.

---

## Housekeeping to do along the way

Nothing open. Done in #37: the CI smoke test takes its commands from
`pyproject.toml` (and the example plugin's), and `tests/test_docs.py` checks
that `config.example.toml`, the README's `[commands]` block and its command
table match them.
