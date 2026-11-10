# Plan: log in to the web console from another computer

Status: planned, nothing built yet · Requested 2026-11-10

## Goal

Today the web console (item 10) answers only on `127.0.0.1`: an admin has
to sit at the node's computer. In an emergency the node may be in a closet
or another room, so admins should be able to open the console from a
laptop or phone on the same network, with a login that's safe to type on
that network.

The local console stays exactly as it is (the `console.url` link and its
key, opened with `mesh-contingency-console`). Remote access is a second,
separate listener that is off unless turned on.

## Decided (2026-11-10)

- **Credential: a password plus a 6-digit code** from an authenticator app
  (TOTP, RFC 6238), both asked at every login.
- **One login per admin.** Each login belongs to one admin key in
  `users.toml [admin]`; what it does runs as that admin, so `history` says
  `by <name>` (not `by console`) and rate limits are that admin's. Removing
  the key from `[admin]` ends the login at the next request.
- **HTTPS with a certificate the bot makes itself** on first start
  (self-signed). Each browser warns once; the admin checks the fingerprint
  the bot prints, and on the local console's Dashboard, against the one the
  browser shows. Optional: `cert` and `key` in `[console]` to use your own.
  Works with no internet, which suits a contingency node.
- **The whole local network may reach it:** any device that can reach the
  node gets the login page. As a guard against a port forward or a
  misconfigured router, requests from public (internet) addresses are
  refused before the login page: only private, link-local and loopback
  addresses (10/8, 172.16/12, 192.168/16, 169.254/16, 100.64/10 for
  Tailscale-style VPNs, fc00::/7, fe80::/10) are answered.

## How it fits together

```
 laptop / phone on the LAN                       the node's computer
 ┌──────────────────┐   HTTPS :8738   ┌─────────────────────────────────┐
 │ browser          │ ──────────────▶ │ bot                             │
 │  login page:     │                 │  remote listener (0.0.0.0, ::)  │
 │  name, password, │                 │   1. source address private?    │
 │  6-digit code    │                 │   2. Origin check (not GET)     │
 └──────────────────┘                 │   3. session cookie, or login   │
                                      │   4. same API + app as local    │
 browser on the node                  │                                 │
 ┌──────────────────┐   HTTP :8737    │  local listener (127.0.0.1)     │
 │ console.url link │ ──────────────▶ │   unchanged: Host check + key   │
 └──────────────────┘                 └─────────────────────────────────┘
                                         console_logins.json (0600)
                                         console_tls/ cert + key (0600)
```

Both listeners serve the same API (`web/api.py`) and the same app; only
the guard in front differs. The API learns who is asking from the request
(the local key → `console`, a session → that admin), instead of always
using `CONSOLE`.

## Logins

Kept in `console_logins.json` next to `config.toml`, readable only by the
bot's account (like `console.url`), never in `users.toml` or a backup's
plain text. Each login:

```json
{"name": "sam", "admin": "<admin public key>",
 "password": "scrypt$n=32768,r=8,p=1$<salt>$<hash>",
 "totp": "<base32 secret>", "last_step": 0, "created": 1762790000}
```

- **Passwords** are hashed with `hashlib.scrypt` (standard library, no new
  dependency), a 16-byte random salt each, and compared in constant time.
  At least 12 characters; no other rules.
- **TOTP**: 30-second steps, 6 digits, SHA-1 (what every authenticator
  app expects), the step before and after accepted for clock drift, and a
  code is refused if its step is not after `last_step` (so a code seen
  over a shoulder can't be used again).
- Made and changed on the node's computer only, never from the browser:

  ```sh
  mesh-contingency-console login add sam --admin <key or name>
  mesh-contingency-console login password sam    # a new password
  mesh-contingency-console login code sam        # a new authenticator secret
  mesh-contingency-console login remove sam      # also ends its sessions
  mesh-contingency-console login list
  ```

  `add` asks for the password twice (not echoed), then prints the
  authenticator secret as a QR code in the terminal and as text, and asks
  for one code from the app before saving, so a mistyped secret can't
  lock you out. The bot rereads the file when it changes; no restart.

## Sessions and lockout

- After a good login: a random 32-byte session id in a cookie,
  `Secure; HttpOnly; SameSite=Strict; Path=/`, kept in the bot's memory
  only (a restart logs everyone out). It ends after 30 minutes without a
  request, or 12 hours after login, whichever is first, and on **Log out**.
- Failed logins: after 5 failures in 15 minutes for a name, or 10 from
  one address, that name or address waits 15 minutes. The answer is the
  same for a wrong name, password or code (`Wrong name, password or
  code.`), and takes as long.
- Every login, failure, lockout and logout is printed to the journal
  (`Console login: sam from 192.168.1.20`), never the password or code.
  Repeated failures are a node watch problem (`Node problem: 12 failed
  console logins in 15 min`), so admins hear about it over the radio.

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

`remote = true` with no logins in `console_logins.json` starts the
listener but says `Remote console: no logins yet; add one with
mesh-contingency-console login add`.

## The app

- A **Log in** page (name, password, code) shown when the API answers
  401 on the remote listener; the local console never shows it.
- The header says who is logged in, with **Log out**.
- Nothing else changes: the same pages, the same confirmations.

## PRs

1. **This plan** and the roadmap entry (item 20).
2. **Logins file and command:** scrypt, TOTP, `console_logins.json`, the
   `login` subcommands, and tests. Nothing listens yet.
3. **The remote listener:** HTTPS (made or given certificate), the
   source-address guard, login/logout API, sessions, lockout, journal
   lines; the API acting as the logged-in admin (`history` by name, their
   rate limits). Tests with aiohttp's test client.
4. **The app's login page** and logged-in header; README (Web console,
   Security notes), `config.example.toml`, the wiki Admin Guide (held
   until merged).
5. **Node watch:** failed-login bursts as a node problem.

## To check on the real node

- Log in from a laptop and a phone on the home network; the certificate
  warning shows the same fingerprint the bot printed.
- A wrong code, a reused code and a removed admin are all refused.
- The local `console.url` link still works as before, with no login page.
- A restart logs remote sessions out; the local console opens as usual.
- From outside the network (phone on cellular) it can't be reached.
