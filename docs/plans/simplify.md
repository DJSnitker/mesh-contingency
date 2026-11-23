# Plan: weather alerts on the Public channel, plus a reusable command library

Status: planned, nothing changed yet · Requested 2026-11-23 · Decisions settled 2026-11-23

## Goal

Mesh Contingency does two things:

- It watches the National Weather Service for the counties in `config.toml` and posts each new alert to MeshCore's **Public** channel.
- It answers two commands from its admins: `alert` (post a message to Public) and `testalert` (post the test message now).

The command machinery moves out into its own library, **`mesh-commands`**. That library has no imports from Mesh Contingency, so it can be lifted into another project as is. Everything else is archived (tag `archive/full-system`, branch `archive/full`), not deleted, so git can bring it back. The README, the wiki and the installer describe only what's left.

## Decisions (settled 2026-11-23)

1. **Commands:** keep `alert` and `testalert`, admin only, plus `help` so admins can see them.
   - Remove `wx`.
   - `area` goes too: it needs the console's weather reports (`area_weather.py`).
   - All other commands are archived.
2. **Weekly test message:** keep it, on Public. It's off unless `weekly` is set.
3. **Alert filter:** add one, so advisories and statements stay off a shared channel.
4. **Version:** 1.0.0.
5. **NOAA Weather Radio (roadmap item 19):** keep it as the one future item.
6. **Command library:** a separate package in this repo, `packages/mesh-commands/`. It has its own `pyproject.toml`, README, tests and LICENSE. Its import name is `mesh_commands`. The name can still change before step 3.

## What stays in Mesh Contingency

| Part | Today | After |
|---|---|---|
| `weather.py` | NWS requests, county codes, conditions | Only the alert and county-code parts. The conditions code goes with `wx`/`area`. |
| `alerts.py` | Watcher, hashtag channels, test message | Watcher, test message and filter. Posts to Public. No hashtag-channel code. |
| `commands/alert.py`, `commands/testalert.py` | Post to `#contingency-wx` | Post to Public. Built on `mesh_commands`. |
| `bot.py` (697 lines) | Commands, users, console, contacts, adverts, watch, backups | Connects to the radio, runs the alert tasks, and hands DMs to `mesh_commands`. Reconnects and logs. About 200 lines. |
| `contacts.py` | Auto-add with limits, notices and lookalike checks | Auto-adds **only admins' adverts**, so the node can reply to them. |
| `[advert]` | Scheduled and startup adverts | Unchanged. Admins' radios need it to find the node. |
| `state.py`, `alerts.json` | Many counters and logs | Only what alerts need: county codes and the alerts already posted. |
| `install.sh` | Node, console, channels, first admin | Node only. Asks for counties and, optionally, the first admin key. `--check` stays. |
| `deploy/mesh-contingency.service` | systemd user unit | Unchanged. |
| CI | 13 jobs | Tests (3.11–3.14) for both packages, Lint, Install script, a wheel smoke test, and a check that `mesh_commands` never imports `mesh_contingency`. |

The config:

```toml
[alerts]
counties = ["Taylor, TX", "Jones, TX"]
every_minutes = 10
severity = ["Extreme", "Severe"]   # the filter; leave it out to post everything
# events = ["Tornado Warning", "Severe Thunderstorm Warning"]  # or name the events

[alert_test]                       # optional
weekly = "Wednesday 17:00"
timezone = "America/Chicago"

[admins]                           # who may send alert and testalert
keys = ["<64-hex public key>"]

[advert]
every_hours = 12
flood = true

[commands]
help = { permission = "admin" }
alert = { permission = "admin" }
testalert = { permission = "admin" }
```

The admin keys move from `users.toml` into `config.toml`, so there's one file. With no admin keys, the alerts still run and the commands answer no one.

## The `mesh-commands` library

It holds what any MeshCore bot needs to answer direct-message commands, taken from today's `api.py`, `registry.py`, `running.py`, `limits.py`, `output.py`, `testing.py` and the DM handling in `bot.py`:

| Module | Contents | From |
|---|---|---|
| `command.py` | `Command`, `@command`/`FunctionCommand`, `CommandResult`, `CommandError`, `Sender`, `Context`, `Confirmations` | `api.py` |
| `replies.py` | `MAX_REPLY_LEN`, `MAX_PARTS`, `fit_reply`, `split_reply`, `pack`, `page`, `to_messages` | `api.py` |
| `permissions.py` | The levels: public, user, admin, disabled. A `Roles` protocol (`is_user(key)`, `is_admin(key)`), and `KeyRoles(users, admins)`, a set-based version. | `api.is_authorized` |
| `registry.py` | Entry-point discovery under a group name the project picks, `handler = "module:attr"`, and parsing `[commands]` (permission, timeout, rate, options). An unknown command or level is an error. | `registry.py` |
| `limits.py` | `parse_rate`, `RateLimiter`, `describe_rate`, `wait_text` | `limits.py` (without `EmailLog`) |
| `running.py` | Running a command with a timeout, with the answer and its timing | `running.py` |
| `dispatch.py` | `Dispatcher`: parse a DM, suggest the nearest command name, check permission and rate, run, split the reply and send it. It takes a `send(key, text)` callable, so it doesn't depend on the radio. | `bot.py` (`parse_command`, `nearest_command`, `on_message`, `reply_unrecognized`) |
| `meshcore.py` | `attach(mc, dispatcher)`: subscribes to direct messages, works out who sent each one from the radio's contacts, and sends replies. This is the only module that imports `meshcore`. | `bot.py` (`get_sender`, `send_dm`) |
| `output.py` | `SafeOutput`/`printable`, which keeps senders' text from adding terminal escapes to the log | `output.py` |
| `builtin/help.py` | `help`, which lists the commands the sender may use | `commands/help.py` |
| `testing.py` | `FakeMeshCore`, `make_context`, `make_contact`, `event` | `testing.py` |

Things the library leaves out:

- Mesh Contingency's users file, state, email limits and console senders.
- Anything about weather or channels.

`Context` drops `directory`, `state` and `limits`. It keeps `name`, `options`, `radio`, `commands` and `send`, plus `roles` and an `extras` dict for whatever the host project wants to pass in. For Mesh Contingency, that's the alert settings.

Its README has:

- a 20-line example bot
- writing a command, as a class and with `@command`
- the `[commands]` config
- permissions and rate limits
- testing with `FakeMeshCore`

Mesh Contingency installs it from the repo: `pip install -e packages/mesh-commands -e .`. The `install.sh` script and CI do the same. It can move to its own repo later with `git subtree split --prefix packages/mesh-commands`, keeping its history.

## What is archived

These come off `main` and stay on the archive tag (step 0):

- **Commands:**
  - all in `mesh_contingency/commands/` except `alert`, `testalert` and `help` (`help` moves to the library)
  - the old plugin entry points
  - `examples/mesh-dice`, which can return as the library's example later
- **Users:**
  - `directory.py` and `names.py`
  - `users.toml` and `users.example.toml`
  - `join`/`approve`
  - the users-file backups
- **Mailbox and email:**
  - `msg` and `inbox`
  - `sealing.py` and `ENCRYPTION_NOTES.md`
  - `qm`, `email` and `emailall`
  - the email limits
- **Check-ins and the roster:** `status`, `ok`, `checkins`, `roster`.
- **The extras in contacts:**
  - auto-adding everyone
  - new-contact notices
  - the lookalike checks
  - the `contact`/`contacts`/`radio`/`advert` commands
- **The admin watch:** `watch.py`. Problems show in the journal and in `install.sh --check`.
- **Backups:** `backup.py` and `[backup]`.
- **Weather lookups:** `wx`, `area`, `alertmap`, and the conditions code in `weather.py`. County codes are still looked up once and kept in `alerts.json`; deleting that file makes the bot look them up again.
- **Bible verses:** `bible/` and `verse`.
- **The web console and remote console:**
  - `web/` and `console/`
  - `console_tls/` and `console_users.json`
  - `channel_log.py` and `area_weather.py`
  - the `mesh-contingency-console` command and the `[console]` extra
- **The phone and desktop apps:** `app/` and their CI builds. Their APK and installers stay attached to the old GitHub releases.
- **Docs:**
  - the old plans in `docs/plans/`
  - the wiki's User App Guide, User Guide, Admin Guide and Commands pages
  - the architecture deck

## Posting to Public

- MeshCore's Public channel has a fixed key, the same on every radio (`PUBLIC_SECRET` in `alerts.py`). The bot and `alert` post to the slot with that key, usually slot 0. They never add or rename a channel.
- If no slot has the Public key:
  - the watcher logs `No Public channel on the radio`
  - `alert` and `testalert` reply that there's no Public channel
  - `--check` reports it as a blocker
- What carries over unchanged:
  - one message per distinct alert, even when several counties share it
  - the spacing between messages
  - the `<node name>: <text>` length limit
  - never posting the same alert twice, even across restarts
- **The filter.** `severity` matches the NWS's severity field: Extreme, Severe, Moderate, Minor, Unknown. `events` matches event names exactly, ignoring case. An alert is posted if it passes every filter that's set. With neither set, everything is posted, as it is today. An alert that's filtered out is still recorded as seen, so changing the filter later doesn't post old alerts.

## Steps

Each step is its own PR. Tests and lint must pass after each one.

0. **Archive.**
   - Tag the current `main` (344769a) `archive/full-system` and push it.
   - Push a branch, `archive/full`, from the same commit, so it shows on GitHub. (A tag and a branch with the same name would make git's refs ambiguous.)
   - On that branch, copy the current wiki pages into `docs/wiki-archive/`.
   - Add a GitHub release, "Full system (archived)", pointing at the tag.
1. **Remove the apps and the console.**
   - Delete `app/`, `console/` and `web/`, along with `channel_log.py` and `area_weather.py`.
   - Delete the `[console]` extra, the console entry point and their CI jobs (Web console app, Phone app, Android, three Desktop builds).
   - `bot.py` stops starting the console. `area` goes with `area_weather.py`.
2. **Remove the other commands, users and the rest.**
   - Delete everything in "What is archived" that's still on `main`, and the tests that cover it.
   - Move the admin keys to `[admins] keys`. An old `users.toml` with `[admin] keys` is still read, with a warning saying to move them, until 1.1.
   - Cut `contacts.py` down to admins only.
   - Old sections in an existing `config.toml` (`[backup]`, `[watch]`, `[console]`, `[limits]`, …) get one warning at startup that lists them, and are otherwise ignored. They don't stop the bot, so your node keeps running through the upgrade.
3. **Extract `mesh-commands`.**
   - Create `packages/mesh-commands/` with the modules above and move their tests there.
   - `alert`, `testalert` and `bot.py` import from `mesh_commands`. Nothing about the commands changes.
   - CI runs the library's tests on their own, in a fresh environment without `mesh_contingency` installed, and fails if `mesh_commands` imports it.
   - The library README and its own CHANGELOG start at 0.1.0.
4. **Post to Public, and add the filter.**
   - Remove `channel` from `[alerts]` and `[commands.alert]`, and the hashtag-channel code. An old `channel` setting gets a warning and is ignored.
   - Add the Public-slot lookup, the "no Public channel" error and the filter.
   - Tests:
     - Public in slot 0
     - Public in another slot
     - no Public channel
     - `alert` and `testalert` to Public
     - severity and events filters, together and apart
     - a filtered alert not posted after the filter changes
5. **The installer.**
   - Drop `--console`, `--alert-channel`, `--comm-channel`, the `users.toml` copy and the example-admin-key blocker.
   - Install both packages.
   - On a new install:
     - Ask for counties, e.g. `Taylor, TX; Jones, TX`.
     - Optionally ask for the first admin's public key. An empty answer adds a to-do line.
   - `--check`:
     - Blockers: no counties set, no Public channel.
     - A note: no admin keys, so `alert`/`testalert` answer no one.
     - It waits for the watcher's start line.
   - Update the CI install job.
6. **The docs.**
   - Rewrite the README to about 200 lines: what it does, install, config (with the filter), admins and the two commands, check it, update, troubleshoot, uninstall.
   - Add a CHANGELOG 1.0.0 entry listing every removal and pointing at the archive tag.
   - Make `docs/plans/roadmap.md` short: what's done, and NWR (item 19) next. Its plan, `weather-radio.md`, changes to post to Public.
   - The other plans live only on the archive branch.
   - Cut `config.example.toml` to the sections above.
7. **Wiki** (after step 6 merges):
   - Home.
   - Set Up a Node, with the systemd page folded in.
   - Weather Alerts: counties, the filter, the test message, what a post looks like.
   - Admin Commands: `alert`, `testalert`, `help`, and how to add yourself as an admin.
   - Troubleshooting.
   - Delete the other pages and the deck, and update the sidebar to match.
   - The held edits from #141/#142 are superseded. The `--check` text is reused; the channel questions are dropped.
8. **Release 1.0.0, then move your node over.**
   - Back up `config.toml`, `users.toml` and the `*.json` files first.
   - Run `install.sh` to update.
   - In `config.toml`, add `[admins] keys` from `users.toml`, and delete the old sections the startup warning lists.
   - Run `install.sh --check`.
   - Try `alert test` from your radio, then watch for the Wednesday test on Public.
   - Once it runs, delete the leftover files: `users.toml`, `mailbox.json`, `requests.json`, `history.json`, `status.json`, `watch.json`, `backup.json`, `area_weather.json`, `console_users.json*` and `console_tls/`. Keep `adverts.json`, which the advert schedule still uses.

## Risks

- **A busy Public channel.** Alerts on Public reach people who didn't ask for them. The filter, the one-post-per-alert rule and the spacing are the defences. A suggested starting filter is `severity = ["Extreme", "Severe"]`.
- **Nothing tells admins about problems.** With the watch gone, a problem like no internet or an unplugged radio shows only in the journal. `--check` and `journalctl --user -u mesh-contingency` are the ways to look.
- **People using the old features lose them.** Anyone with a mailbox, or who checks in with `ok`, loses that. Their data stays in the step 8 backup, and the code stays on the archive tag.
- **The library is cut from one project.** Its API will be shaped by Mesh Contingency until a second project uses it. It starts at 0.1.0 so it can change without a major version.
