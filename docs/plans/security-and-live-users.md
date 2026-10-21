# Plan: security hardening and a live user directory

Status: done (PR #3, then sections 3 and 5 of `user-management-and-robustness.md`)

## Goals

1. Close the risks found in the security review (identity forgery, missing rate
   limits, contact flooding, terminal escape injection) plus the smaller
   hardening items.
2. Move users and admins out of `config.toml` into their own file that the bot
   reloads while running, so people can be added, removed or given new email
   addresses without restarting the bot.

Both goals change how people are identified and stored, so they are planned
together: the new user file is where full public keys (item 1 of the review)
will live.

## Order of work

| Phase | What | Review item | Why this order |
|---|---|---|---|
| 1 | Live user directory (`users.toml`) with full public keys | new + #1 | Everything below reads users/admins from it |
| 2 | Identity verification and key-collision protection | #1 | Depends on full keys from phase 1 |
| 3 | Per-sender rate limits and an email cap | #2 | Independent; highest abuse impact after #1 |
| 4 | Contact flood controls and notice batching | #3 | Builds on the notice code |
| 5 | Safe console output | #4 | Small, touches logging everywhere; do once the rest is stable |
| 6 | Hardening: address check, file permissions, pinning | #5–#7 | Small, independent |

Each phase is its own commit (or small PR) with tests, so it can be reviewed and
merged on its own. CI must pass at every step.

---

## Phase 1: live user directory

*Status: done.* Built as planned, with full keys required (no prefixes) and
one addition: a change is applied only once the file has looked the same on
two checks in a row, so an editor's half-written save is never loaded (the
`reload` command and SIGHUP apply it at once). Admin changes reload too.

### File layout

Users and admins move to `users.toml` (git-ignored), next to `config.toml` by
default. `config.toml` keeps the static settings (commands, contacts, limits)
and names the file:

```toml
# config.toml
[directory]
file = "users.toml"        # relative to config.toml
reload_seconds = 5         # how often to check the file for changes
```

```toml
# users.toml
[admin]
keys = ["<64-hex public key>"]

[users.<64-hex public key>]
name = "Alice"
quickim = "someone@example.com"
emailall = ["a@example.com", "b@example.com"]
```

- A `users.example.toml` with placeholders is committed; `users.toml` is added
  to `.gitignore`.
- **Migration:** if `config.toml` still has `[users]` or `[admin]`, the bot
  stops with a message saying to move them to `users.toml`, so there is never
  doubt about which copy is in effect. Doug's local files are migrated as part
  of this phase.
- **Keys:** full 64-hex public keys only; a prefix stops the bot with an error.
  *Done ahead of the rest of phase 1:* `config.toml` `[users]`/`[admin]` now
  require full keys, `Sender.key` became `Sender.public_key`, and full keys
  are never logged (the console shows the 12-hex prefix).

### Live reload

- A `Directory` object holds the current snapshot (users, admins, load time).
  Every reader asks it at the moment of use; nothing copies users at startup.
- A background task checks the file's modification time and size every
  `reload_seconds` (standard library only, no file-watcher dependency; works
  with editors that save by writing a new file and renaming it).
- On change: parse and fully validate the new file, then swap the snapshot in
  one step. **If the new file is invalid, the old snapshot stays in effect**,
  the error is logged, and admins get a DM ("users.toml not reloaded: <reason>"),
  so a typo never locks everyone out.
- Each successful reload logs a summary: `users.toml reloaded: +Bob, -Carol,
  Alice changed; admins unchanged`.
- New admin command `reload` forces an immediate check and replies with the
  same summary. `SIGHUP` does the same from the shell.
- Admin changes take effect on reload like any other change. Because the file
  grants admin rights, the bot warns at startup and on reload if it is writable
  by anyone but its owner (see phase 6).

### Code changes

- `registry.py`: `load_users`/`load_admins` move to a new `directory.py` with
  `Directory.load(path)`, validation and the reload task.
- `api.py`: `Context` gets `directory`; `ctx.users` and `ctx.admins` become
  read-only properties returning the *current* snapshot, so existing plugins
  keep working and see changes. `is_authorized` takes the directory.
- `quickim.py` / `emailall.py`: look up the sender's addresses at execute time
  instead of building `recipients` in `__init__`; `enabled` becomes "any user
  currently has addresses", and the startup warning becomes a per-reload one.
- `bot.py`: startup counts and the new-contact notice read admins from the
  directory each time.

### Tests

- Load, validate, reject: bad keys, unknown keys, wrong types, both files
  defining users.
- Reload swaps atomically; an invalid edit keeps the old snapshot and notifies
  admins; deleting the file keeps the old snapshot.
- A user added to the file can run a user command on the next message without
  a restart; a removed user is refused; a changed `quickim` address is used.
- `reload` command and `SIGHUP` trigger a reload; non-admins can't run `reload`.
- Plugins reading `ctx.users` see updates.

---

## Phase 2: identity verification

*Status: done.* Alerts name the prefix, not the full key, since full keys are
never logged. The shared-prefix check runs at startup, after each users-file
reload and when a message arrives from a shared prefix (not on every
contacts refresh).

Problem: senders are identified by a 6-byte key prefix, and auto-add accepts any
node, so a node with a forged matching prefix would be treated as an admin or
user.

- **At authorization time** (*done*): a sender gets user/admin rights only if
  1. exactly one radio contact has that prefix, and
  2. that contact's full public key equals the full key in the config.
  Otherwise they are treated as unknown (public commands only).
- **At auto-add:** a new node whose prefix matches a configured user/admin but
  whose full key differs is **not added**, and admins get a DM:
  `Blocked a1b2c3d4e5f6 Alice: posing as Alice (same key prefix, different key)`,
  once per node.
- **At startup and after each contacts refresh:** if the radio already holds two
  contacts sharing a configured prefix, log it, alert admins once, and refuse
  that prefix until resolved.
- **Replies** (*done*): `send_dm` looks the contact up by full key when known,
  so a reply can never go to the impostor.

Tests: impostor with matching prefix is refused and alerted; legitimate user
with full key passes; prefix-only user still works with a warning; duplicate
prefixes in the radio block privileged commands; replies go to the right key.

---

## Phase 3: rate limits

*Status: done, as section 3 of `user-management-and-robustness.md`* (limits
are set as `public_rate`/`user_rate`/`admin_rate` in `[limits]`).

- Per command, in its `[commands]` entry: `rate = "5/hour"` (also `/minute`,
  `/day`). Counted per sender per command with a sliding window, in memory
  (resets on restart; noted in the README).
- Defaults when unset: public commands `10/hour`, user commands `30/hour`,
  admin commands unlimited. Defaults live in `[limits]` in `config.toml`.
- Email cap across `quickim`, `emailall` and `email` together:
  `[limits] emails_per_day = 50` per sender, plus a bot-wide cap
  (`emails_per_day_total = 200`) to protect the Gmail account.
- When limited, reply once `wx: limit reached, try again in 23 min`, then stay
  silent for that sender and command until the window frees up, so the limit
  itself can't be used to generate traffic.

Tests: limits per sender and per command are independent; window expiry (fake
clock, as the cooldown tests do); one notice then silence; email caps across
all three commands; bot-wide cap.

---

## Phase 4: contact flood controls

*Status: done, as section 3 of `user-management-and-robustness.md`, without
pruning or a separate pending-notice limit.*

- `[contacts] max_new_per_hour = 20`: beyond this, new nodes are skipped (they
  are picked up when they advertise again later). Users and admins in the
  directory are always added, regardless of the cap.
- **Notice batching:** at most `notices_per_hour = 5` individual admin notices;
  after that, one summary per hour: `14 more new contacts in the last hour
  (3 skipped by the cap)`.
- **Pending-notice limit:** the background send queue holds at most a handful
  of notices; extras fold into the summary, so notices can never delay replies
  for long.
- **Optional pruning** (`prune_after_days = 30`, off by default): when the
  radio's contact table is over 80% full, remove chat contacts that haven't
  advertised in N days, never users or admins. Uses the radio's reported
  capacity if available; otherwise this sub-step is deferred.

Tests: cap and hourly reset; users/admins bypass the cap; batching and summary
text; queue never grows past its limit; pruning respects protected contacts.

---

## Phase 5: safe console output

*Status: moved to section 5 of `user-management-and-robustness.md`.*

- One helper, `printable(text)`, that replaces control characters (except
  newline in multi-line command output) with visible escapes like `\x1b`.
- Applied to everything that came from the mesh before it is printed: message
  text, node names, contact labels, command console output, error text.

Tests: ANSI color/clear-screen and OSC title sequences are escaped; normal text,
accents and emoji are unchanged.

---

## Phase 6: hardening

*Status: moved to section 5 of `user-management-and-robustness.md`.*

- `ADDRESS_RE`: the first character must be a letter or digit (no leading `+`
  or `%`).
- Startup and reload warn if `config.toml`, `users.toml` or `~/.mailrc` can be
  read or written by other accounts, with the `chmod 600` command to fix it.
- CI: pin GitHub Actions to commit SHAs with the version as a comment
  (Dependabot keeps them updated).
- Pin `meshcore` to the tested range (`>=2.3.17,<2.4`), with Dependabot
  proposing upgrades.

---

## Documentation

- README: new "Users file" section (format, live reload, `reload`, migration),
  "Limits" section, updated security notes; remove the reliance on prefixes.
- `config.example.toml` / new `users.example.toml`.
- Writing a command: `ctx.users` / `ctx.admins` are live; don't cache them.

## Decisions needed before starting

1. ~~**Prefix-only keys**~~: decided — full keys required from day one.
2. **Default limits:** are `10/hour` (public), `30/hour` (user) and
   `50 emails/day` per user reasonable for your mesh?
3. **Live admin changes:** reload admins too (planned), or only reload users and
   require a restart to change admins?
4. **Pruning:** include in phase 4, or leave for later?
5. **Future:** should admins be able to add/remove users over the mesh
   (e.g. `user add <key> <name>`), with the bot writing `users.toml`? Not in
   this plan; the live file makes it possible later.
