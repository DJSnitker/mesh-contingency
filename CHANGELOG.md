# Changelog

What changed in each release of mesh-contingency. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (while below 1.0, a minor version
may change how the bot is configured).

## [Unreleased]

## [0.8.1] - 2026-10-23

`wx` looks up a county as well as a zipcode. Pull request #60.

### Changed

- **`wx` takes a county as well as a zipcode:** `wx Taylor, TX` (or
  `taylor county tx`, or its NWS code `wx TXC441`) gives the weather at the
  county's middle and the alerts issued for the county. `wx 79601` works as
  before.

### Upgrading from 0.8.0

```sh
git pull
```

Then restart the bot. Nothing in `config.toml` changes, and the console
needs no rebuild.

## [0.8.0] - 2026-10-23

The web console now manages the radio itself: its contacts, its channels and
what's said on them, and its settings (name, power, position, clock, reboot,
frequency), and it shows the weather for the watched counties. It opens with
one command. And the bot sets the radio's clock at each start. Pull requests
#53 to #58.

### Added

- **`mesh-contingency-console`** opens the web console in the browser, on
  the node's computer: no more copying the link out of `console.url`. It
  checks the bot answers the link first, and says why if not (console off,
  bot not running, an old link), then opens it. The "Open the console's
  link" page mentions it.
- **Area Weather**, a new page in the web console after the Dashboard: a
  card for each county in `[alerts] counties`, whether or not there's an
  alert, with the latest
  reading from the nearest NWS station (temperature, conditions, wind,
  humidity), the next three forecast periods with their chance of rain, and
  the alerts out for it (the alert watcher's, not another request). The bot
  asks the NWS every 15 min and keeps the last report: when the internet is
  down, a card shows how old it is and why. Each county's middle and nearest
  stations are looked up once and kept in `area_weather.json`. New in the
  API: `/api/weather`.
- **Alerts on the Dashboard:** a row above Watch names the weather alerts out
  now, each with its counties (*Wind Advisory (Taylor, Jones)*), in orange,
  or says *none*, or that they can't be checked; it links to Area Weather.
  `/api/overview` has them as `alerts`.
- **`contact remove|path <name or key>`** (admins): take a contact off the
  radio, which holds only so many, or reset the path to one whose messages
  stopped getting through. Removing asks first, and says if the contact is a
  user or an admin, since they can't be messaged until they advert again.
  Add `contact = { permission = "admin" }` under `[commands]` to turn it on.
- **Contacts on the Radio page** of the web console: the radio's contacts,
  how many of how many, each with its type, whether it's a user or an admin,
  its path (direct, hops, or none) and when it was last heard, a filter, and
  **Reset path** and **Remove** buttons (Remove asks to confirm). New in the
  API: `/api/contacts`.
- **Channels on the Radio page:** the radio's channel slots in use, each
  with its name, whether it's Public, a hashtag channel (anyone who adds the
  name can read it) or private, and what the bot posts there. Keys are never
  shown. New in the API: `/api/channels`. Contacts and channels share a
  panel, a tab each.
- **Channel messages in the web console:** a channel on the Radio page opens
  to what the radio heard on it since the bot started, newest first (who,
  when, the hops and the signal), and what this node posted there; read
  again every 10 s while open. With the console on, the bot keeps the last
  200 of each channel in memory only: nothing is written to disk, and a
  restart forgets them. It still takes no commands from channels. New in the
  API: `/api/channels/{slot}/messages`, and a count and the newest time for
  each slot in `/api/channels`.
- **More of the admin commands in the web console:** **Post alert test**
  (`testalert`, which asks first, as it goes out on the air) and **Look up
  counties again** (`alertmap`) on Area Weather, and **Reload users file**
  (`reload`) on Users.
- **`radio`**, an admin command (`radio = { permission = "admin" }` under
  `[commands]`): the radio's name, frequency, bandwidth, SF and CR with the
  MeshCore presets that match, TX power, position, clock and firmware. Over
  the mesh it only shows them; from the web console it changes them:
  `radio name`, `power`, `position`, `clock`, `reboot` (asks first) and
  `freq` (a preset or the four values; asks first and says how to go back).
  After a reboot or a new frequency the bot stops with an error, for the
  service to start it again. The console's Radio page has a **Settings** tab,
  first, with a form for each, and the frequency set apart: it waits for the
  node's name to be typed. New in the API: `/api/radio` (never the radio's
  Bluetooth PIN).
- **The radio's clock is set at startup** from the computer's when it's 5 s
  or more off (`Set the radio's clock from the computer's: it was 4h 2m
  behind.`): the radio keeps no time across a reboot or a power cut, and
  dates its messages and adverts by it.

### Changed

- **The node watch doesn't announce a reboot from the web console**
  (`radio reboot`, `radio freq`) as a problem; it's only logged.
- **The web console's menu:** the Dashboard first, set apart by a line, then
  the other pages A–Z.
- `scripts/demo_console.py`: the web console on made-up data, to try it
  without a node and to take the wiki's screenshots (`--screenshots DIR`).

### Upgrading from 0.7.0

```sh
git pull
.venv/bin/python -m pip install -e ".[console]"   # or -e . without the console
cd console && npm ci && npm run build && cd ..     # if you use the console
```

The install adds the `mesh-contingency-console` command. The two new admin
commands are off until listed under `[commands]` in `config.toml`:

```toml
contact = { permission = "admin" }
radio = { permission = "admin" }
```

Then restart the bot. Area Weather, the radio's contacts and channels, and
setting the radio's clock need nothing new; the console can change the
radio's settings only with `radio` turned on.

## [0.7.0] - 2026-10-23

The node can be run from a browser on its own computer: the web console
shows the node at a glance and does everything an admin does over the radio,
without a radio in hand or 133-character replies. And a restart of the
computer no longer reads as a problem with the radio. Pull requests #41,
#43, #45, #46, #48, #50 and #51.

### Added

- **Web console** (`[console]` in `config.toml`, off by default; needs
  `pip install -e ".[console]"` and, from a git checkout, `npm ci && npm run
  build` in `console/`): the bot serves a web app on `127.0.0.1:8737`, opened
  with the link it prints at each start and writes to `console.url`. Its
  pages:
  - **Dashboard:** users, join requests, check-ins and messages waiting, the
    node watch, backups, `health`, and the live log.
  - **Users:** every user and admin with Whois, Reset passphrase and Remove,
    and the join requests with Approve and Deny.
  - **Check-ins:** who has checked in and who hasn't, with Clear check-ins.
  - **Inbox:** who has messages waiting, from whom, read or sealed, never
    what they say.
  - **History:** admin actions, newest first, with a filter.
  - **Send:** post to `#contingency-wx` or `#contingency-comm`, or leave a
    message in a user's inbox.
  - **Radio:** Advert, Flood advert and Back up now.

  It runs the same commands as over the radio, as the admin `console`: the
  same checks, rate limits and confirmations (with a Confirm button), and
  history `by console`. It answers only this computer, needs the key from
  the link (then a cookie), refuses other hosts and origins, and sends a
  strict Content-Security-Policy. Its fonts are bundled, so it works without
  the internet, and the Python package ships the app built. See
  [Web console](README.md#web-console).
- **A JSON API** under the console, for scripts on the node's computer:
  `/api/overview`, `/api/users`, `/api/requests`, `/api/checkins`,
  `/api/inbox`, `/api/history`, `/api/commands`, `POST /api/run` (a command's
  whole reply, with `asks` and `ok`) and `/api/log` (server-sent events).
- **For command authors:** `CommandResult(asks=True)` marks a reply that
  only asks to confirm; `own = True` keeps a command acting on the sender's
  own records off the console; `sends = True` offers a user command that only
  leaves something for someone else (as `msg`).

### Changed

- **Node watch** no longer calls it a problem when the radio restarted because
  the computer did (USB power comes back with it): on Linux it says `Node
  restarted: the computer started 1m ago, and the radio with it` instead.
- **Auto alerts** wait up to 2 minutes for the network before the first check,
  so right after the computer starts, `health` doesn't show `last check
  failed` just because the network wasn't up yet.

### Upgrading from 0.6.0

Nothing changes unless you turn the web console on. To update:

```sh
git pull
.venv/bin/python -m pip install -e .
```

and restart the bot. To use the web console:

1. Install its extra, and build its app (needs Node.js 22.22+ or 24.15+;
   the bot itself doesn't):
   ```sh
   .venv/bin/python -m pip install -e ".[console]"
   cd console && npm ci && npm run build && cd ..
   ```
2. Add to `config.toml`:
   ```toml
   [console]
   enabled = true
   ```
3. Restart the bot, and open the link it prints (`Web console:
   http://127.0.0.1:8737/?key=...`), also in `console.url`, in a browser on
   that computer. Each restart makes a new link.

After later updates that change `console/`, run `npm ci && npm run build`
there again before restarting.

## [0.6.0] - 2026-10-22

The node now looks after itself: admins get a direct message when something
goes wrong with it (a low battery, the radio restarting or lost, email
failing...) and when it's over, and the bot's data is backed up every day.
Users who mistype a command are told the one they meant. Pull requests
#33, #34, #36 and #37.

### Added

- **Node watch** (`[watch]` in `config.toml`, on by default): every admin gets
  a direct message when a problem with the node starts and when it's over: a
  low battery, the radio restarting, messages not delivered, email failing,
  repeated command errors, or a users file that can't be reloaded. Each
  problem is announced at most once an hour. `health` shows `watch: no
  problems` or the current ones. When the bot stopped because it lost the
  radio, it says for how long once the radio is back (`Node problem: the
  radio was disconnected for 7m (reconnect_failed); back now`). "Ok again"
  needs evidence (an email sent, a message delivered, a backup made; 30
  minutes for command errors), so a restart of the bot doesn't end a problem
  by itself.
- **Backups** (`[backup]` in `config.toml`, on by default): once a day the
  bot copies its data (`config.toml`, `users.toml`, the JSON files and the
  users file's backups) into a new dated folder in `to` (default
  `~/MeshContingencyBackups`), keeping the newest 7, with permissions kept.
  Best on a separate disk; the bot notes at startup when it isn't. A failed
  backup is retried hourly and reported by the node watch.
- **`backup`** (admins): make a backup now.
- **Suggestions for mistyped commands:** a user or admin who sends
  `resetpassword` gets `unknown command resetpassword; did you mean
  resetpass? help lists yours`, naming only commands they may run (an old
  name like `quickim` gets `qm`). Strangers still get only `unrecognized
  user or function`.

### Changed

- The users-file notice to admins now reads `Node problem: users.toml not
  reloaded: ...`, and is followed by `Node ok again: users.toml reloaded`
  once the file is fixed (unless `[watch] enabled = false`).

### Upgrading from 0.5.0

1. Stop the bot, then update and reinstall, which registers the new
   command:
   ```sh
   git pull
   .venv/bin/python -m pip install -e .
   ```
2. **Turn on `backup`** under `[commands]` in `config.toml`, or the bot
   names it as disabled at startup:
   ```toml
   backup = { permission = "admin" }
   ```
3. Optionally, send the backups to another disk (a USB stick, a second
   drive), which survives this one failing; without it they go to
   `~/MeshContingencyBackups`:
   ```toml
   [backup]
   to = "/mnt/usb/MeshContingencyBackups"
   ```
   The node watch needs no setting; see `[watch]` in `config.example.toml`
   to change its thresholds.
4. Start the bot. The startup log shows `Backups: every 24 h to ...` and
   `Watching the node every 5 min: ...`; the first backup is made straight
   away.

## [0.5.0] - 2026-10-22

Admins can now reach everyone at once with news on a second public channel,
`#contingency-comm`, and see at a glance who has checked in and who hasn't.
When an email can't be sent, the sender is told why. Pull requests #29–#31.

### Added

- **`comm <message>`** (admins): posts to a second public hashtag channel,
  `#contingency-comm`, for news and updates everyone should see at once.
  The channel is added to the radio at startup, like the alert channel.
  Pull requests #29 and #30.
- **`checkins [page <n>]`** (admins): a roll call of every user with their
  last check-in, or `missing`, five to a page.

### Changed

- **Email failures say why.** When `qm`, `emailall` or `email` can't send,
  the reply gives the cause (`qm: not sent, no internet at the node; try
  again later`) instead of `qm: failed`; the full reason goes to the
  console, and `health` shows the last failure. The unsent message is no
  longer left in `~/dead.letter` by s-nail, and a failed email doesn't
  count toward the daily limits. Pull request #31.

### Upgrading from 0.4.0

1. Stop the bot, then update and reinstall, which registers the new
   commands:
   ```sh
   git pull
   .venv/bin/python -m pip install -e .
   ```
2. **Turn on the new commands** under `[commands]` in `config.toml`, or the
   bot names them as disabled at startup:
   ```toml
   checkins = { permission = "admin" }
   comm = { permission = "admin" }
   ```
3. Start the bot. The startup log shows
   `comm: #contingency-comm is channel slot 2.` (or whichever slot was
   free). Ask people to add the hashtag channel `#contingency-comm` in their
   app.

## [0.4.0] - 2026-10-21

Weather alerts no longer need an admin: the bot watches a list of counties
and posts each new National Weather Service alert to the alert channel by
itself, and tests the channel every week. `alert` becomes the admins' way to
post their own message there. Pull requests #26 and #27. Tested on one node
and radio, with the first weekly test posted on 2026-10-21.

### Added

- **Automatic weather alerts** (`[alerts]` in `config.toml`): the bot checks
  the National Weather Service for the listed `counties` (`"Taylor, TX"`)
  every `every_minutes` (default 10) and posts each new alert to the alert
  channel once, named by county, with no admin needed. Each county's NWS
  code is looked up once and kept, so each round is a single request for
  every county. Already-posted alerts are kept in `alerts.json` too, so a
  restart doesn't repost. Posts show in `history` as by "auto", and `health`
  shows when it last checked. Off unless counties are listed.
- **`alertmap [county, ST]`** (admins): look up the NWS codes of the watched
  counties again; replies with one list of county names.
- **Weekly alert test** (`[alert_test]` in `config.toml`): a test message on
  the alert channel at a set day and time each week (`weekly = "Wednesday
  17:00"`, in `timezone`, daylight saving included), followed by the watched
  counties, and **`testalert`** (admins) to post it on request. `health`
  shows the next one.

### Changed

- **`alert <message>`** posts an admin's own message to the alert channel,
  instead of a zipcode's NWS alerts (the automatic alerts do that now, and
  `wx <zipcode>` shows a zipcode's alerts to anyone).

### Removed

- `weather.fetch_alerts`, which only the old `alert` used. A plugin calling
  it can use `weather.county_alerts`, or `fetch_weather(zipcode)["alerts"]`.

### Upgrading from 0.3.0

1. Stop the bot, then update and reinstall, which registers the new
   commands:
   ```sh
   git pull
   .venv/bin/python -m pip install -e .
   ```
2. **Turn on the new commands** under `[commands]` in `config.toml`, or the
   bot names them as disabled at startup:
   ```toml
   alertmap = { permission = "admin" }
   testalert = { permission = "admin" }
   ```
3. **`alert` now takes a message.** `alert 79601` would post the text
   "79601" to the channel. Tell your admins; for a zipcode's alerts, use
   `wx 79601`.
4. Optionally, **watch counties** for automatic alerts, and **test the
   channel weekly** (see `config.example.toml`):
   ```toml
   [alerts]
   counties = ["Taylor, TX", "Jones, TX"]

   [alert_test]
   weekly = "Wednesday 17:00"
   timezone = "America/Chicago"
   ```
   The bot keeps what it has looked up and posted in `alerts.json` next to
   `config.toml`.

## [0.3.0] - 2026-10-21

The node becomes something a group can rely on in an emergency: people join
and are managed over the mesh, leave each other messages (sealed with a
passphrase if they like), check in, and get weather alerts, and the bot runs
as a service that looks after itself. Pull requests #1–#24.

Tested on one radio so far; field testing with more radios is still to come
(see `docs/plans/roadmap.md`), and anything it finds will go into a 0.3.x
release.

### Added

- **Users file.** Users and admins move from `config.toml` to their own
  `users.toml`, keyed by full public keys. The bot reloads it while running
  (every 5 seconds, on `reload`, or on SIGHUP), applies a change only once the
  file is complete and valid, and keeps the previous users if an edit is bad,
  telling the admins why.
- **Joining:** `join` (anyone) asks the admins to become a user; `approve`
  lists and approves requests, `deny` turns one down.
- **User management for admins:** `users`, `whois`, `remove`, `resetpass`.
  For users: `whoami` and `leave`. `remove`, `resetpass` and `leave` ask
  first and act only when sent again within 5 minutes. Nobody can be made an
  admin over the mesh.
- **Messages between users:** `msg <name> <message>`, read with `inbox` and
  cleared with `clearinbox`. Up to 20 wait per person, for 30 days, with a
  short "new message" notice.
- **Sealed messages:** after `setpass <passphrase>`, messages to that user
  are stored sealed (scrypt and X25519) and opened only with
  `inbox <passphrase>`; the bot keeps only the public half of the key.
- **Check-ins:** `ok [status]` and `status <name>` (anyone), `clearstatus`
  (admins).
- **Weather alerts:** `alert <zipcode>` posts the National Weather Service
  alerts for a zipcode to the `#contingency-wx` channel; `wx` shows alerts
  first.
- **Users' own email settings:** `setqm`, `addgroup`, `cleargroup`.
- **Node tools for admins:** `contacts` (the radio's contacts, with users and
  admins marked), `roster` (who has messaged the node since it started),
  `health` (radio, battery, users, messages, errors, emails and the users
  file in one report), `history` (what admins have done, kept across
  restarts), `reload`.
- **Adverts** from the console while the bot runs (`advert`, `advert flood`,
  `contacts`), and on a schedule (`[advert]` in `config.toml`).
- **Contacts:** new contacts are announced to the admins, and the admins are
  warned when an impostor shares a user's key prefix.
- **Limits** (`[limits]`): rate limits by sender level (`public_rate`,
  `user_rate`, `admin_rate`) and daily email caps per sender and for the whole
  node (`emails_per_day`, `emails_per_day_total`). Mailbox messages expire
  after 30 days (`keep_days` in `[commands.msg]`).
- **Running as a service:** a systemd user unit (`deploy/`), with
  step-by-step instructions in the wiki. The bot exits when the radio is lost
  so systemd restarts it, and stops cleanly on SIGTERM.
- **Backups:** the users file is saved to `backups/` before every change the
  bot makes; the newest 5 are kept.
- **Documentation:** a wiki with every command A–Z, a User Guide, an Admin
  Guide and the service guide; a logo and styled README.
- **CI** on GitHub Actions: tests on Python 3.11–3.14, lint, a package and
  plugin install check, and Dependabot.

### Changed

- **Names are the radios' names.** A user is always known by their radio's
  name, exactly as it's advertised (spaces and punctuation included). `join`
  uses it, and the bot updates `users.toml` when a radio's name changes. A
  name with spaces can be put in parentheses: `msg (Sam T-Deck) hi`. Radio
  names with no name, control characters, parentheses or profanity are
  refused at `join`.
- **`quickim` is now `qm`** (quick message), and `setquickim` is `setqm`.
- **Keys are full public keys** (64 hex characters) everywhere in the users
  file; the 12-character prefixes of 0.2.0 are refused.
- The README command table is grouped by who can run each command.

### Security

- Everything the bot prints has terminal control codes escaped, so mesh text
  can't clear or recolour the terminal, set its title or rewrite lines.
- Email addresses typed on the mesh must be plain `user@domain.tld`, starting
  with a letter or digit; subjects have control characters stripped.
- Warnings at startup and on every users-file reload if `config.toml`,
  `users.toml` or `~/.mailrc` can be read by other accounts.
- State files (`mailbox.json`, `status.json`, `requests.json`,
  `history.json`) are created readable only by the bot's account.
- `meshcore` is held to the tested range (`>=2.3.17,<2.4`), and CI's GitHub
  Actions are pinned to commit SHAs.

### Upgrading from 0.2.0

1. Stop the bot, then update and reinstall, which registers the new commands
   and installs `pycryptodome`:
   ```sh
   git pull
   .venv/bin/python -m pip install -e .
   ```
2. **Move `[admin]` and `[users.*]` out of `config.toml`** into a new
   `users.toml` next to it (see `users.example.toml`). The bot refuses to
   start while they are still in `config.toml`, and says so. Replace each
   12-character key prefix with the **full** public key (64 hex characters,
   shown in the MeshCore app). `name` can be left out: the bot fills in each
   radio's name.
3. **Rename `quickim` to `qm`**: in `[commands]` in `config.toml`, and for
   each user in `users.toml`. If you miss one, the bot warns at startup and
   keeps working: it uses an old `[commands]` line for `qm`, and converts
   users' `quickim` addresses itself, with a backup.
4. **Turn on the new commands** by copying the lines you want from the
   `[commands]` section of `config.example.toml`. A command with no line is
   off, and the bot names it at startup (`... has no [commands.<name>]
   section; disabled.`).
5. Make the settings files private, as the bot will remind you:
   ```sh
   chmod 600 config.toml users.toml ~/.mailrc
   ```
6. Optionally, run it as a service: see "Running as a systemd Service on
   Linux" in the wiki.

[0.8.1]: https://github.com/DJSnitker/mesh-contingency/releases/tag/v0.8.1
[0.8.0]: https://github.com/DJSnitker/mesh-contingency/releases/tag/v0.8.0
[0.7.0]: https://github.com/DJSnitker/mesh-contingency/releases/tag/v0.7.0
[0.6.0]: https://github.com/DJSnitker/mesh-contingency/releases/tag/v0.6.0
[0.5.0]: https://github.com/DJSnitker/mesh-contingency/releases/tag/v0.5.0
[0.4.0]: https://github.com/DJSnitker/mesh-contingency/releases/tag/v0.4.0
[0.3.0]: https://github.com/DJSnitker/mesh-contingency/releases/tag/v0.3.0
