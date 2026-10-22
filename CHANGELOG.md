# Changelog

What changed in each release of mesh-contingency. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (while below 1.0, a minor version
may change how the bot is configured).

## [Unreleased]

### Added

- **Node watch** (`[watch]` in `config.toml`, on by default): every admin gets
  a direct message when a problem with the node starts and when it's over: a
  low battery, the radio restarting, messages not delivered, email failing,
  repeated command errors, or a users file that can't be reloaded. Each
  problem is announced at most once an hour. `health` shows `watch: no
  problems` or the current ones.

### Changed

- The users-file notice to admins now reads `Node problem: users.toml not
  reloaded: ...`, and is followed by `Node ok again: users.toml reloaded`
  once the file is fixed (unless `[watch] enabled = false`).

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

[0.5.0]: https://github.com/DJSnitker/mesh-contingency/releases/tag/v0.5.0
[0.4.0]: https://github.com/DJSnitker/mesh-contingency/releases/tag/v0.4.0
[0.3.0]: https://github.com/DJSnitker/mesh-contingency/releases/tag/v0.3.0
