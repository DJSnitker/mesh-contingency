# Roadmap: after the user-management plan

Status: proposed, nothing started · Written 2026-10-21

Every earlier plan is built (`security-and-live-users.md`,
`private-mailbox.md`, `user-management-and-robustness.md`; PRs #1–#18). This
lists what to do next, in the recommended order. Each item is its own branch
and PR, with tests, README and wiki updates, like the earlier work.

| # | What | Kind | Size | Status |
|---|---|---|---|---|
| 1 | Field testing on real radios | testing, no code | small | to do |
| 2 | Release 0.3.0 with a changelog | release | small | to do |
| 3 | Automatic weather alerts | feature | medium | to do |
| 4 | Admin broadcast to every user | feature | small | to do |
| 5 | Roll call of check-ins | feature | small | to do |
| 6 | Queue emails while the internet is down | feature | medium | to do |
| 7 | Alerts to admins about the node itself | feature | medium | to do |
| 8 | Off-machine backups of the bot's data | operations | small | to do |
| 9 | Does the radio restart when the bot connects? | check, docs | small | to do |

Recommended order: 1, then 2, then 3. Items 4–9 can follow in any order; 4
and 5 are quick wins, 6 and 7 matter most when things go wrong.

---

## 1. Field testing on real radios

Everything below has passed unit tests but hasn't been tried end to end on
radios. Watch the journal (`journalctl --user -u mesh-contingency -f`) during
each; anything that fails becomes a bug fix before item 2.

- **Service, reboot:** reboot without logging in; `help` from another radio
  gets an answer.
- **Service, lost radio:** unplug the radio while the bot runs, wait, plug it
  back in. Expect `Lost the radio (...); stopping.`, a restart about 30 s
  later, then `Connected to ...`. While unplugged, the log should show
  `No serial device found` every 30 s.
- **Sealed messages:** `setpass <12-16 chars>`; another user sends `msg`;
  `inbox` shows only who and when; `inbox <passphrase>` shows the text;
  `inbox <wrong>` is refused; `clearinbox`. Check `mailbox.json` holds
  `sealed`, not the text.
- **Joining (names are radios' names, PR #18):** `join` from a radio named
  with a space (e.g. `Sam T-Deck`) asks under exactly that name; `join` from a
  radio with a profane name is refused; `approve «Sam T-Deck»` works.
- **Names with spaces:** `msg sam t-deck hi` and `msg «Sam T-Deck» hi` both
  reach the user; `whois «Sam T-Deck»` shows them; `status sam` finds their
  check-in.
- **Renamed radio:** rename a user's radio in the app, send the node any
  command from it; the log shows `... is now <new name>, the radio's name`,
  `users.toml` has the new name, and `history` lists it as by `radio`.
- **Admin tools:** `approve`, then `history` lists it; `backups/` holds the
  previous `users.toml`; `health` reflects the new user; `remove` asks before
  acting.
- **Limits:** a burst of `wx` from a public sender gets one "limit reached"
  reply, then silence.

## 2. Release 0.3.0 with a changelog

`pyproject.toml` still says `0.2.0` although PRs #5–#16 added a lot.

- Bump `version` to `0.3.0`.
- New `CHANGELOG.md` (Keep a Changelog style): an entry for 0.3.0 summarising
  sealed mailboxes, user management, limits, adverts and `contacts`,
  names taken from the radios (with `« »` for names with spaces, and
  `rename` removed) and the profanity filter, the systemd service, `health`,
  `history` and backups, the hardening, the wiki and logo. Note what existing
  nodes must do on upgrade: add the `[commands]` lines for new commands
  (`health`, `history`, `contacts`, the user commands), delete the
  `rename` line (it only warns), `chmod 600` on
  `~/.mailrc`, re-run `pip install -e .`.
- Tag `v0.3.0` and publish a GitHub release with the changelog entry
  (`gh release create v0.3.0 --notes-file ...`).
- Decide: does CI need a release workflow (build and attach the wheel), or is
  a tag enough? Suggest: a tag and notes only for now.

## 3. Automatic weather alerts

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

## 4. Admin broadcast to every user

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

## 5. Roll call of check-ins

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

## 6. Queue emails while the internet is down

In an emergency the internet may come and go, and today `quickim`,
`emailall` and `email` just fail.

- When `mail` fails (non-zero exit or timeout), save the email to
  `outbox.json` (git-ignored, mode 600) and reply
  `quickim: no internet; queued, will send when it's back`.
- A background task retries the outbox every few minutes, oldest first, and
  DMs the sender `quickim to partner@example.com: sent (queued 2h ago)` when
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

## 7. Alerts to admins about the node itself

Problems shouldn't wait for someone to send `health`.

- A background check every few minutes; each condition DMs every admin
  once when it starts and once when it clears:
  - battery below a threshold (e.g. 3.5 V; configurable);
  - the radio restarted (its uptime went backwards) while the bot didn't;
  - N undelivered replies in a row, or the outbox (item 6) growing;
  - repeated command errors (e.g. `wx` timing out = internet down);
  - `users.toml` not reloadable (already sent today; fold in here).
- At most one notice per condition per hour, so a flapping value can't
  flood the mesh.
- **Config:** `[watch]` with thresholds and an `enabled` switch.
- **Depends on:** item 9 (whether a bot restart also restarts the radio)
  for the restart check.

## 8. Off-machine backups of the bot's data

A dead disk would lose the users, messages, check-ins and history.

- Document (wiki, Admin Guide or the systemd page) a nightly copy with a
  systemd user timer: `config.toml`, `users.toml`, `*.json`, `backups/` to
  another disk, USB stick or machine (`rsync`), keeping permissions.
- Optionally ship `deploy/mesh-contingency-backup.service` and `.timer`
  using `rsync -a` to a destination set in one line.
- Warn in the docs: the copies hold email addresses, keys and messages
  (sealed ones stay sealed); keep the destination private.

## 9. Does the radio restart when the bot connects?

`health` showed `radio up` close to the bot's own uptime, which suggests the
Heltec V3 restarts whenever its USB serial port is opened (common on ESP32
boards).

- Check: note the radio uptime from `health`, `systemctl --user restart
  mesh-contingency`, send `health` again. If `radio up` reset, it restarts
  on connect.
- Document the result in the wiki (Commands: `health`; Admin Guide: Check the
  node's health): when `radio up` shorter than `up` means a real radio
  restart.
- Feeds item 7's restart check.

---

## Housekeeping to do along the way

- The CI smoke test lists command names by hand; consider deriving the list
  from `pyproject.toml`'s entry points so new commands can't be forgotten.
- `config.example.toml` and the README's example `[commands]` block repeat
  each other; a test could check they match.
