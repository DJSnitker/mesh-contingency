# Plan: a web console for the node

Status: done, released in 0.7.0 (#43, #45, #46, #48, #50, #51, and this release PR) · Requested 2026-10-22

## Goal

Everything an admin does over the radio (watch the node, manage users and
join requests, see check-ins and the inbox, post alerts, send messages, make
backups) can also be done from a browser on the bot's own computer, without a
radio in hand and without the 140-character replies.

## Decisions (2026-10-22)

- **This computer only.** The console listens on `127.0.0.1`; no phone or
  laptop access over the network. Nothing to log in to (but see
  [Safety](#safety-on-this-computer): the link carries a key).
- **First version:** a dashboard; users and join requests; check-ins, inbox
  and history; posting and sending. Each is its own PR.
- **In this repo, served by the bot.** An Angular app in `console/`; its
  build ships inside the Python package, and the bot serves it and its API.
  One install, one version, one service.
- **Styled like the marketing site** (`mesh-contingency-marketing`): the same
  palette (`docs/branding`), fonts, buttons, panels and stroke icons.

## How it fits together

```
browser ── http://127.0.0.1:8737/?key=... ──> bot process
                                              ├─ static files: the Angular build
                                              ├─ /api/...: JSON, reads Directory and State
                                              ├─ /api/run: runs a command as "console"
                                              └─ /api/log: live log (server-sent events)
```

**Inside the bot, not beside it.** Only the bot can talk to the radio (one
program per serial port), and it owns `users.toml` and the JSON files while
it runs. A separate program would fight it for both. So the web server runs
as one more asyncio task in the bot, like the node watch and backups, and
stops with it.

**Actions go through the commands.** The console doesn't reimplement approve,
remove, alert or msg. It runs the same command objects the radio does, as a
built-in admin sender named `console`, so the checks, the "send it again to
confirm" for `remove`, the history entries (`by console`) and the replies are
exactly what a radio admin gets. The console shows the reply in full (no
140-character paging). Reading is different: lists (users, requests,
check-ins, history) come straight from `Directory` and `State` as JSON, so
the console can show tables instead of paged text.

**Live log.** What the bot prints already goes through `SafeOutput`; it will
also keep the last few hundred lines in memory and send new ones to open
consoles (server-sent events). Private commands are already left out of the
log, so passphrases and message text never reach the console this way.

**Sealed messages stay sealed.** The inbox view shows who has mail, from whom
and when, as `inbox` does without a passphrase; never the text of a sealed
message.

## Safety on this computer

Listening on `127.0.0.1` stops other machines, but not two things on this
one:

- **Web pages in the admin's own browser.** Any site can make the browser
  send requests to `127.0.0.1`, and with DNS rebinding can even read the
  answers. So the server only answers requests whose `Host` is
  `127.0.0.1:<port>` or `localhost:<port>`, and changes (POST) need a
  matching `Origin` too.
- **Other accounts on the computer**, which can reach `127.0.0.1` as well.
  So, as Jupyter does, the bot makes a random key at each start, writes the
  console's address with it to `console.url` (mode 600, next to
  `config.toml`) and prints it in the journal (readable only by this account
  and admins of the computer). The first visit with `?key=` sets a cookie
  (`HttpOnly`, `SameSite=Strict`) and drops the key from the address bar;
  every API call needs the cookie. A restart makes a new key: open the new
  link.

Nothing is listened on unless `[console] enabled = true`, and `host` can't be
set to anything but `127.0.0.1` or `localhost` (the bot refuses to start
otherwise), so a config mistake can't expose it to the network.

```toml
[console]
enabled = true
port = 8737     # 127.0.0.1 only
```

## The app

- **Angular 22** (as the marketing site), standalone components, signals,
  no extra UI library. `console/` has its own `package.json`.
- **Styles:** the marketing site's tokens (`--ink`, `--orange`, `--sky`,
  ...), `Barlow Condensed` / `Inter` / `JetBrains Mono`, `.btn`, panels and
  the `app-icon` set, copied in. The fonts are **bundled**, not loaded from
  Google Fonts: the console must work when the internet is down, which is
  when it matters most.
- **Pages:** Dashboard · Users · Check-ins · Inbox · History · Send ·
  Radio (advert and backup, apart from the messages; added in PR 6). A left
  rail on wide screens, a top bar on narrow ones.
- **Build:** `npm run build` in `console/` writes to
  `mesh_contingency/web/static/` (not committed); the wheel includes it.
  CI's package job builds the console before the wheel and checks it's in
  there; a new CI job lints and tests the Angular app. Without a build (a
  plain `git pull` with no `npm run build`), the bot says so at startup and
  the API still works.

## Server side

- **aiohttp** for the server: asyncio-native, small, with server-sent events.
  An optional extra, `pip install -e ".[console]"`, so a node without the
  console doesn't need it; with `enabled = true` and aiohttp missing the bot
  says how to install it and starts without the console.
- New module `mesh_contingency/web/` (`server.py`, `api.py`), tests with
  aiohttp's test client.

| Endpoint | What |
|---|---|
| `GET /api/overview` | health items, watch problems, last backup, radio battery/uptime, counts |
| `GET /api/users` | users and admins: name, key prefix, settings, last seen, check-in |
| `GET /api/requests` | join requests waiting |
| `GET /api/checkins` | statuses, who's missing |
| `GET /api/inbox` | mailboxes: recipient, count, senders and times (no sealed text) |
| `GET /api/history` | admin actions, newest first |
| `GET /api/commands` | commands the console may run, with usage |
| `POST /api/run` | `{"command": "approve", "text": "Sam T-Deck"}` → the full reply |
| `GET /api/log` | the recent log, then new lines as they come |

## PRs, in order

1. **This plan** (docs only).
2. **Server**, split in two (decided 2026-10-22). No app yet; usable with
   `curl`.
   - **2a (done, #43):** `[console]`, the key and cookie, Host/Origin
     checks, the read endpoints (`mesh_contingency/web/`); `health`'s items
     shared with `/api/overview`; aiohttp as the `.[console]` extra.
   - **2b (next):**
     - Move the core of running a command (authorization, rate limit,
       timeout, `CommandError` / failure handling, `CommandResult`) out of
       `on_message` in `bot.py` into one function the radio and the console
       both call, so they can't differ.
     - The console sender: `Sender("console", <a reserved key>)`, which
       `is_authorized` treats as an admin (decided: no entry in
       `users.toml`). History reads `by console`.
     - `GET /api/commands`: admin and public commands only (user commands
       like `inbox`, `setpass`, `whoami` act on the sender's own mailbox or
       settings, which `console` doesn't have), with usage.
     - `POST /api/run` `{"command", "text"}`: the full reply, not paged;
       `remove`'s "send it again to confirm" works as over the radio.
     - `GET /api/log`: `SafeOutput` keeps the last ~500 lines and sends new
       ones as server-sent events; a test that private commands' text never
       appears.
3. **App shell and dashboard:** `console/` with the styles, fonts, icons and
   layout, the dashboard and live log; build into the package; CI.
4. **Users and join requests:** tables, approve/deny, remove (with the
   confirmation), whois, resetpass.
5. **Check-ins, inbox and history.**
6. **Send:** post to `#contingency-wx` and `#contingency-comm`, a direct
   message, backup and advert buttons.
7. **Docs and release 0.7.0:** README, wiki (an Admin Guide page), changelog.

## Not in the first version

- Access from other devices (would need real logins and HTTPS).
- Editing `config.toml` from the browser (a restart is needed anyway, and a
  mistake there stops the bot).
- Reading sealed messages.
