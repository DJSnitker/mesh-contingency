# Plan: console users, logging in from the network

Status: built, PRs 2–6 (#121–#125); wiki Admin Guide updated; left: the checks on the real node below · Requested 2026-11-10 · Redone 2026-11-10

## Goal

Today the web console (item 10) answers only on `127.0.0.1`: an admin has
to sit at the node's computer. In an Emergency Operations Center the node
may be in a closet or another room, and the people running it work from
whatever laptop, tablet or phone is at hand. They should be able to open
the console from any device on the EOC network and log in.

**Console users are their own users, separate from the mesh.** They have
nothing to do with radios, `users.toml` or `[admin]`: a console user needs
no radio, and owning a radio, even an admin's, gives no way into the
console. Two zones:

| Zone | Who | How they're known | Where they act |
|------|-----|-------------------|----------------|
| Mesh | users and admins in `users.toml` | their radio's full public key | over the radio |
| Console | console users in `console_users.json` | name + password | over HTTPS, from the browser |

Neither zone can create or change the other's identities through its own
login. A console user still manages mesh users (approve, remove, set
email...) through the console's pages, as today's console does.

The local console stays as it is (the `console.url` link and its key,
opened with `mesh-contingency-console`): it is for whoever sits at the
node. Remote access is a second listener, off unless turned on.

## Decided (2026-11-10)

- **Console users, not tied to radios** (above). The first version of
  this plan tied each login to an admin's radio key; that was dropped.
- **One role.** Every console user can do everything the console does
  today, the radio's settings included, and manage the other console users.
- **Made on the node first, then from the console.** The first console
  user is made with a command on the node's computer. After that, any
  logged-in console user can add, reset and remove others from a
  **Console users** page.
- **Password only**, no authenticator code: at least 12 characters, scrypt,
  with lockout after failed tries (below).
- **HTTPS with a certificate the bot makes itself** on first start
  (self-signed). Each browser warns once; the user checks the fingerprint
  the bot prints, and the local console's Dashboard shows, against the one
  the browser shows. Optional: `cert` and `key` in `[console]` to use your
  own. Works with no internet.
- **Local network only:** any device that can reach the node gets the
  login page, but requests from public (internet) addresses are refused
  before it, as a guard against a port forward or a misconfigured router.
  Only private, link-local and loopback addresses (10/8, 172.16/12,
  192.168/16, 169.254/16, 100.64/10 for Tailscale-style VPNs, fc00::/7,
  fe80::/10) are answered.

## How it fits together

```
 EOC laptop / tablet / phone                     the node's computer
 ┌──────────────────┐   HTTPS :8738   ┌─────────────────────────────────┐
 │ browser          │ ──────────────▶ │ bot                             │
 │  login page:     │                 │  remote listener (0.0.0.0, ::)  │
 │  name, password  │                 │   1. source address private?    │
 └──────────────────┘                 │   2. Origin check (not GET)     │
                                      │   3. session cookie, or login   │
 browser on the node                  │   4. same API + app as local    │
 ┌──────────────────┐   HTTP :8737    │                                 │
 │ console.url link │ ──────────────▶ │  local listener (127.0.0.1)     │
 └──────────────────┘                 │   unchanged: Host check + key   │
                                      └─────────────────────────────────┘
                                         console_users.json (0600)
                                         console_tls/ cert + key (0600)
```

Both listeners serve the same API (`web/api.py`) and the same app; only
the guard in front differs.

## Who did it

Today the API runs everything as one sender, `api.CONSOLE`
(`Sender("console", "console")`), whose key isn't hex so no radio can be
it. Each console user becomes a sender of the same kind:
`Sender("<name>", "console:<name>")`. Not hex, so no radio is ever one.

- The API takes the sender from the request: the local key → `CONSOLE`
  (as today), a session → that console user.
- `api.is_authorized` lets admin commands through for any console sender
  (`public_key == "console"` or starting `console:`), as it does for
  `CONSOLE` now. A helper `api.is_console(sender)` replaces the
  `== CONSOLE.public_key` checks, such as `radio`'s "changes only from the
  web console" (`commands/radio.py`).
- `history` says `by sam (console)`, not `by console`, and the journal
  lines print `[sam (console)]`. Rate limits are kept per console user.
- Console users get no mesh rights: they are not in `users.toml`, can't be
  messaged over the radio and can't run commands by radio.

## Console users

Kept in `console_users.json` next to `config.toml`, readable only by the
bot's account (like `console.url`), never in `users.toml`, and left out of
backups (`[backup]`): after a restore, a console user takes a minute to
make again. In `{"users": [...]}`:

```json
{"name": "sam", "password": "scrypt$32768$8$1$<salt>$<hash>",
 "created": 1762790000, "created_by": "node", "changed": 1762790000}
```

- **Names:** 1–32 characters, letters, digits, `.`, `_`, `-`, compared
  without case. Kept apart from radio names; a console user may share a
  name with a mesh user, and history's `(console)` tells them apart.
- **Passwords** are hashed with `hashlib.scrypt` (standard library, no new
  dependency), a 16-byte random salt each, compared in constant time. At
  least 12 characters; no other rules. Never printed, logged or sent back.
- **On the node's computer**, always available (the way back in if every
  console user is locked out or forgotten):

  ```sh
  mesh-contingency-console user add sam        # asks for the password twice
  mesh-contingency-console user password sam   # a new password
  mesh-contingency-console user remove sam     # also ends their sessions
  mesh-contingency-console user list
  ```

- **From the console**, a **Console users** page (both listeners): list
  (name, made when and by whom, last login), add (name + password typed
  twice), set a new password, remove. Removing asks first, as other
  removals do. A user can't remove themselves, so the last one can't be
  removed from the browser. Each change goes in `history`
  (`console user sam added by alex (console)`), never the password.
- **Changing your own password** from the header menu asks for the
  current one first.
- The bot rereads the file when it changes, so the command's changes
  apply without a restart. A removed user, or one whose password changed,
  is logged out at their next request.

## Sessions and lockout

- After a good login: a random 32-byte session id in a cookie,
  `Secure; HttpOnly; SameSite=Strict; Path=/`, kept in the bot's memory
  only (a restart logs everyone out). It ends after 30 minutes without being
  used, or 12 hours after login, whichever is first, and on **Log out**.
  The app's own refreshes (pages and unread counts every 10–60 s) are
  marked `X-Console-Background: 1` and don't count as use, so an open
  console left alone logs out too; a live log ends within 15 s of its
  login ending.
- Failed logins: after 5 failures in 15 minutes for a name, or 10 from
  one address, that name or address waits 15 minutes. The answer is the
  same for a wrong name or password (`Wrong name or password.`), and
  takes as long (a dummy scrypt for an unknown name). With no second
  factor this lockout is the main guard, so it can't be turned off.
- `user password` on the node also clears that name's lockout.
- Every login, failure, lockout and logout goes to the journal
  (`Console login: sam from 192.168.1.20`), never the password. Repeated
  failures are a node watch problem (`Node problem: 12 failed console
  logins in 15 min`), so mesh admins hear about it over the radio.

## HTTPS

- On first start with `remote = true` the bot makes `console_tls/cert.pem`
  and `key.pem` (an EC P-256 key, valid 10 years) naming the computer's
  hostname, `<hostname>.local` and its current addresses. That needs the
  `cryptography` package, added to the `[console]` extra.
- It prints `Remote console: https://<address>:8738/ (certificate
  SHA-256 AB:CD:...)` and the local Dashboard shows the same, so the
  fingerprint can be checked against the browser's warning page.
- `mesh-contingency-console cert renew` makes a new one (if the
  computer's address changes, say); browsers then warn once again.
- `cert` and `key` in `[console]` use your own files instead.
- Responses on the remote listener add `Strict-Transport-Security`;
  everything else (CSP, no framing) is as today.

## Config

```toml
[console]
enabled = true
port = 8737            # the local console, 127.0.0.1 only, as today
remote = false         # true: also answer the local network over HTTPS
remote_port = 8738
# cert = "/path/to/cert.pem"   # your own certificate, instead of the bot's
# key = "/path/to/key.pem"
```

`remote = true` with no console users starts the listener but says
`Remote console: no console users yet; add one with
mesh-contingency-console user add`, and the login page says the same.

## The app

- A **Log in** page (name, password) shown when the API answers 401 on
  the remote listener; the local console never shows it.
- The header says who is logged in (`console` on the local one), with
  **Change password** (remote only) and **Log out**.
- A **Console users** page, as above.
- Everything else is the same: the same pages, the same confirmations.

## PRs

1. **This plan** and the roadmap entry (item 20).
2. **Console users file and command:** `console_users.json`, scrypt, the
   `user` subcommands, left out of backups, and tests. Nothing listens yet.
3. **Who did it:** console senders (`console:<name>`), `is_console`, the
   API taking the sender from the request, history and rate limits per
   console user. The local console keeps working as `console`.
4. **The remote listener:** HTTPS (made or given certificate), the
   source-address guard, login/logout and console-user API, sessions,
   lockout, journal lines. Tests with aiohttp's test client.
5. **The app:** login page, header, Console users page; README (Web
   console, Security notes), `config.example.toml`, the wiki Admin Guide
   (after merging: done).
6. **Node watch:** failed-login bursts as a node problem.

## To check on the real node

- Log in from a laptop and a phone on the EOC/home network; the
  certificate warning shows the same fingerprint the bot printed.
- A console user with no radio approves a join, changes a radio setting,
  and both show in `history` by their name.
- A mesh admin's radio can't reach the console, and a console user can't
  run commands over the radio.
- A wrong password locks out after 5 tries; `user password` on the node
  unlocks it. A user removed from the Console users page is logged out
  at their next click.
- The local `console.url` link still works as before, with no login page.
- A restart logs remote sessions out; the local console opens as usual.
- From outside the network (phone on cellular) it can't be reached.
