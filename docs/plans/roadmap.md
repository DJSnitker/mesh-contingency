# Roadmap: after the user-management plan

Status: items 1–2 done; field testing paused · Written 2026-10-21 · Updated 2026-10-21

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
| 3 | Admin broadcast to every user | feature | small | to do |
| 4 | Roll call of check-ins | feature | small | to do |
| 5 | Queue emails while the internet is down | feature | medium | to do |
| 6 | Alerts to admins about the node itself | feature | medium | to do |
| 7 | Off-machine backups of the bot's data | operations | small | to do |
| 8 | Does the radio restart when the bot connects? | check, docs | small | to do |
| 9 | Field testing on real radios | testing, no code | small | paused: waiting on more radios |

Recommended order: items 3–8 can follow in any order; 3 and 4 are
quick wins, 5 and 6 matter most when things go wrong, and 8 needs only the one
radio. Field testing (9) waits for more radio equipment; it was started
2026-10-21 and its results so far are kept below.

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

## 3. Admin broadcast to every user

`broadcast <message>` (admin): a direct message to every user, e.g. "Shelter
open at the high school gym".

- Sent in the background (`send_later`), one at a time, so the reply comes
  straight away: `broadcast: sending to 12 user(s)`.
- The message arrives as `Broadcast from Doug: <message>`, cut to fit one
  mesh message (about 133 characters, minus the prefix); refuse longer text
  rather than split it.
- Asks first, like `remove`: "this sends to 12 user(s). Send it again within
  5 min to confirm." Broadcasts are costly in airtime.
- Recorded in `history`.
- Undelivered count shows up in `health` as usual.
- **Decide:** include admins? Suggest: everyone in the users file except the
  sender.
- **Tests:** all users get it, the sender doesn't; confirmation; length
  limit; history entry.

## 4. Roll call of check-ins

After an event, admins need to see everyone's status at once and who is
missing.

- `checkins [page]` (admin), or `status all`: every check-in, newest first,
  `Sam 2h ago: at the shelter; Alex 5h ago: ok`, paged like `users`.
- `checkins missing`: users with no check-in (or none since a given time,
  e.g. since the last `clearstatus`).
- **Decide:** new command `checkins`, or `status all` / `status missing` on
  the existing public `status` (which would then need an admin check inside)?
  Suggest: a separate admin command, so `status` stays simple and public.
- **Tests:** ordering, paging, missing list, empty states.

## 5. Queue emails while the internet is down

In an emergency the internet may come and go, and today `qm`,
`emailall` and `email` just fail.

- When `mail` fails (non-zero exit or timeout), save the email to
  `outbox.json` (git-ignored, mode 600) and reply
  `qm: no internet; queued, will send when it's back`.
- A background task retries the outbox every few minutes, oldest first, and
  DMs the sender `qm to partner@example.com: sent (queued 2h ago)` when
  one goes out.
- Give up after 24 hours (configurable) and tell the sender.
- Email caps count at queue time, so a queue can't be used to get round them.
- `health` shows `outbox 3`.
- **Decide:** how to tell "no internet" from "bad address / mail
  misconfigured"? `mail` exit codes are not specific. Suggest: queue on any
  failure, and say "failed again" in the log with `mail`'s stderr so a
  misconfiguration is visible.
- **Tests:** failure queues; retry success notifies the sender; expiry;
  caps; survives a restart.

## 6. Alerts to admins about the node itself

Problems shouldn't wait for someone to send `health`.

- A background check every few minutes; each condition DMs every admin
  once when it starts and once when it clears:
  - battery below a threshold (e.g. 3.5 V; configurable);
  - the radio restarted (its uptime went backwards) while the bot didn't;
  - N undelivered replies in a row, or the outbox (item 5) growing;
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
