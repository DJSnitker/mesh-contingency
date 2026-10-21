# Changelog

What changed in each release of mesh-contingency. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) (while below 1.0, a minor version
may change how the bot is configured).

## [Unreleased]

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
  counties again.

### Changed

- **`alert <message>`** posts an admin's own message to the alert channel,
  instead of a zipcode's NWS alerts (the automatic alerts do that now, and
  `wx <zipcode>` shows a zipcode's alerts to anyone).

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

[Unreleased]: https://github.com/DJSnitker/mesh-contingency/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/DJSnitker/mesh-contingency/releases/tag/v0.3.0
