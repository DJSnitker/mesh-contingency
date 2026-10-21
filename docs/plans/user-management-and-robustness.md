# Plan: user management and robustness

Status: all five sections built · Requested 2026-10-20

Builds on the users file (`users.toml`, reloaded while running), the join
flow and the mailbox. Sections 3 and 5 replace phases 3–6 of
`security-and-live-users.md`.

| Section | What | Status |
|---|---|---|
| 1 | Admin user management over the mesh | built |
| 2 | Users' own commands and the new-message notice | built |
| 3 | Abuse protection: rate limits, email caps, contact floods, mailbox expiry | built |
| 4 | Keeping the bot running: service, log file, health, backups, history | built |
| 5 | Small hardening | built |

---

## Shared pieces

- **Finding a user** (`directory.find_user`): the longest user name that
  starts the text (so "Ann Lee hi" isn't for "Ann"), else a key prefix of 4+
  hex characters matching exactly one user. `msg` already works this way;
  every command that names a user uses the same rules.
- **Confirming** (`api.Confirmations`): a destructive command answers the first
  time with what will happen, and acts only if the same command is sent again
  by the same person within 5 minutes. `setpass` already works this way.
- **Removing a section** (`Directory.remove_user`): like `save_user`, the result
  is read back first and nothing is written unless only that user is gone.

## Section 1: admin user management

All admin commands.

| Command | What it does |
|---|---|
| `users [page]` | Every user, by name, with the key prefix and what they have set: `Alice a1b2c3 (pass, quickim, group 3)` |
| `whois <name or key>` | One user: name, key prefix, settings, passphrase yes/no, messages waiting, admin or not |
| `remove <name or key>` | Removes the user's section of the users file and their mailbox, after confirming. Admin rights (`[admin] keys`) are not touched |
| `rename <name or key> <new name>` | Changes a user's name. Names are up to 32 plain characters and must not already belong to another user |
| `resetpass <name or key>` | For a forgotten passphrase: removes the user's `inbox_key` and their sealed messages, after confirming, and tells the user by DM |

Not included: making someone an admin over the mesh. A lost or stolen admin
radio could then create more admins; admin changes stay a file edit.

## Section 2: users' own commands

| Command | What it does |
|---|---|
| `whoami` | What the bot knows about you: name, key prefix, passphrase set or not, quickim and group, messages waiting, admin or not |
| `leave` | Removes you from the users file and deletes your mailbox, after confirming |
| `clearinbox all` | Deletes every message, unread and sealed included |

**New-message notice:** when `msg` saves a message, the recipient gets a DM
`inbox: new message from Bob; send inbox to read`, at most once per 10 minutes
per recipient so a burst of messages sends one notice. It never contains the
text. Not sent for a message to yourself. Turned off with `notify = false` in
`[commands.msg]`.

## Section 3: abuse protection

### Rate limits

- Per command: `rate = "5/hour"` in its `[commands.<name>]` entry (`/minute`,
  `/hour`, `/day`; `rate = "none"` for no limit). Counted per sender per
  command over a sliding window, in memory (resets on restart).
- Defaults by permission level, in `[limits]`: public `10/hour`, user
  `30/hour`, admin none.
- When a sender reaches a limit, they get one reply,
  `wx: limit reached, try again in 23 min`; further messages for that command
  get no reply until the window frees up, so the limit can't be used to make
  the bot transmit.

### Email caps

- `[limits] emails_per_day = 50`: emails sent per sender per day, across
  `quickim`, `emailall` and `email`, one per command however many addresses
  it goes to (an `emailall` is one email with every address in To).
- `[limits] emails_per_day_total = 200`: addresses emailed by the whole bot
  per day (an `emailall` to 3 addresses counts 3), to protect the sending
  account, whose limits count recipients.
- Counted over a sliding 24 hours, in memory.

### Contact flood controls

In `[contacts]`, applying when auto-add is on:
- `max_new_per_hour = 20`: new nodes beyond this are not added (they are added
  when they advertise again later). Nodes of users and admins in the users file
  are always added.
- `notices_per_hour = 5`: individual new-contact notices to admins; after that
  they are counted, and one summary is sent when the hour is up:
  `14 more new contacts in the last hour (3 skipped by the cap)`.

Pruning old contacts is not included; the radio's capacity isn't reported
reliably enough to decide when to prune.

### Mailbox expiry

Messages older than 30 days are deleted, read or not, sealed or not. Set
`keep_days` in `[commands.msg]` (0 keeps them forever).

## Section 4: keeping the bot running

- *Done (PR #12):* a systemd user unit with automatic restart
  (`deploy/mesh-contingency.service`), and the wiki page "Running as a systemd
  Service on Linux". The bot exits when the radio is lost for good, so the
  service restarts it, and stops cleanly on SIGTERM.
- *Done (PR #12):* the log is the systemd journal, which rotates itself
  (private commands stay out of it), rather than a log file of our own.
- *Done:* admin `health`: bot and radio uptime, radio model and firmware,
  battery, contacts against capacity, users, join requests, messages waiting,
  check-ins, messages and replies since start (undelivered counted), errors
  and the last one, emails in 24 hours, last flood advert, and the last
  users-file reload or why it failed. Radio queries time out after 5 s each
  and are left out if unanswered.
- *Done:* a backup of `users.toml` before every write by the bot, in a
  `backups` folder next to it (`users-YYYYMMDD-HHMMSS.toml`, as private as the
  file), keeping the newest 5.
- *Done:* an audit trail in `history.json` of approve, deny, remove, rename,
  resetpass, clearstatus and alert, plus users who leave, with who and when
  (newest 200 kept), read with the admin `history [page]` command.

## Section 5: small hardening

- *Done:* terminal control characters (C0/C1 controls except newline and tab,
  DEL, and Unicode bidi controls) are escaped in everything the bot prints,
  by wrapping its output once (`output.py`) rather than at each print.
- *Done:* email addresses must start with a letter or digit.
- *Done:* startup and every users-file reload warn when `config.toml`,
  `users.toml` or the mail settings (`~/.mailrc` or `$MAILRC`) can be read or
  changed by other accounts, with the `chmod 600` fix.
- *Done:* GitHub Actions pinned to commit SHAs (version in a comment), and
  `meshcore` to `>=2.3.17,<2.4`; Dependabot proposes updates.

## Decisions taken (change if needed)

1. Default limits: public `10/hour`, user `30/hour`, admin none; 50 emails per
   user per day, 200 in total.
2. No admin promotion over the mesh.
3. No contact pruning.
4. `remove` and `leave` delete the person's mailbox; check-ins in
   `status.json` stay.
