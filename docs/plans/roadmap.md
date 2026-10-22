# Roadmap: after the user-management plan

Status: items 1–5 done; field testing paused · Written 2026-10-21 · Updated 2026-10-22 (item 5)

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
| 6 | Alerts to admins about the node itself | feature | medium | to do |
| 7 | Off-machine backups of the bot's data | operations | small | to do |
| 8 | Does the radio restart when the bot connects? | check, docs | small | to check: result not recorded |
| 9 | Field testing on real radios | testing, no code | small | paused: waiting on more radios |

Recommended order: item 6 (matters most when things go wrong), then 7.
Item 8's result isn't written down yet (see its section); item 6's restart
check needs it. Field testing (9) waits for more radio
equipment; it was started 2026-10-21 and its results so far are kept below.

## Resume here (next session)

Where things stood on 2026-10-22:

- **Merged:** #29 (`comm` posting to `#contingency-comm`, `checkins` roll
  call; both admin) and #30 (README for them). The wiki is published for
  both. Item 5 (email failures reported, no queue) is in the PR that
  updates this section; its wiki edits wait for the merge.
- **The node** runs `main` with `comm` and `checkins` as admin in its
  `config.toml`; `#contingency-wx` is channel slot 1 and `#contingency-comm`
  slot 2. The next weekly alert test is Wednesday 2026-10-28, 5:00 PM CDT.
- **Not released:** the changelog has an `[Unreleased]` section for
  `comm`, `checkins` and the email change; 0.5.0 can follow item 6 or go out
  on its own.

Steps, in order:

1. If the computer was restarted, check the service came back:
   `systemctl --user status mesh-contingency`; the journal should show
   `comm: #contingency-comm is channel slot 2.`
2. Item 8, the check (two minutes with a radio): send `health`, note
   `radio up`, `systemctl --user restart mesh-contingency`, send `health`
   again, and write the answer in item 8 below.
3. Then item 6 (admin alerts about the node), which uses item 8's answer
   and folds in repeated email failures; then item 7 (backups).

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

## 6. Alerts to admins about the node itself

Problems shouldn't wait for someone to send `health`.

- A background check every few minutes; each condition DMs every admin
  once when it starts and once when it clears:
  - battery below a threshold (e.g. 3.5 V; configurable);
  - the radio restarted (its uptime went backwards) while the bot didn't;
  - N undelivered replies in a row, or emails failing (item 5);
  - repeated command errors (e.g. `wx` timing out = internet down);
  - `users.toml` not reloadable (already sent today; fold in here).
- At most one notice per condition per hour, so a flapping value can't
  flood the mesh.
- **Config:** `[watch]` with thresholds and an `enabled` switch.
- **Depends on:** item 8 (whether a bot restart also restarts the radio)
  for the restart check.

## 7. Off-machine backups of the bot's data

A dead disk would lose the users, messages, check-ins and history.

- Document (wiki, Admin Guide or the systemd page) a nightly copy with a
  systemd user timer: `config.toml`, `users.toml`, `*.json`, `backups/` to
  another disk, USB stick or machine (`rsync`), keeping permissions.
- Optionally ship `deploy/mesh-contingency-backup.service` and `.timer`
  using `rsync -a` to a destination set in one line.
- Warn in the docs: the copies hold email addresses, keys and messages
  (sealed ones stay sealed); keep the destination private.

## 8. Does the radio restart when the bot connects?

`health` showed `radio up` close to the bot's own uptime, which suggests the
Heltec V3 restarts whenever its USB serial port is opened (common on ESP32
boards).

- Check: note the radio uptime from `health`, `systemctl --user restart
  mesh-contingency`, send `health` again. If `radio up` reset, it restarts
  on connect.
- Document the result in the wiki (Commands: `health`; Admin Guide: Check the
  node's health): when `radio up` shorter than `up` means a real radio
  restart.
- Feeds item 6's restart check.

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

### Checks

- **Service, reboot:** reboot without logging in; `help` from another radio
  gets an answer.
- **Service, lost radio:** unplug the radio while the bot runs, wait, plug it
  back in. Expect `Lost the radio (...); stopping.`, a restart about 30 s
  later, then `Connected to ...`. While unplugged, the log should show
  `No serial device found` every 30 s.
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
  sender's radio name in the subject; `quickim` now gets
  `unrecognized user or function`.
- **Admin tools:** `approve`, then `history` lists it; `backups/` holds the
  previous `users.toml`; `health` reflects the new user; `remove` asks before
  acting.
- **Limits:** a burst of `wx` from a public sender gets one "limit reached"
  reply, then silence.

---

## Housekeeping to do along the way

- The CI smoke test lists command names by hand; consider deriving the list
  from `pyproject.toml`'s entry points so new commands can't be forgotten.
- `config.example.toml` and the README's example `[commands]` block repeat
  each other; a test could check they match.
