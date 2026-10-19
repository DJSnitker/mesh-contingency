# mesh-contingency

A small bot for a [MeshCore](https://github.com/meshcore-dev/MeshCore) companion
radio connected over USB serial. It listens for **direct messages** sent to the
radio, runs simple commands, and replies over the mesh. It is meant as a
contingency link: someone with only a mesh radio can check the weather or get
a message out by email.

Channel messages are ignored entirely; only direct messages are acted on.

## Commands

| Command | Who can run it | What it does |
|---|---|---|
| `wx <zipcode>` | anyone | Current conditions, chance of precipitation and active NWS alerts for a US zipcode. Full report on the console; a ≤133-char summary is sent back, prioritizing alerts, then precipitation, then temperature and wind. |
| `notify_default <message>` | users | Emails the message to the sender's configured default address. |
| `notify_group <message>` | users | Emails the message to the sender's configured group of addresses. |
| `notify_email <address> <message>` | users | Emails the message to the given address. |
| `advert [flood]` | admins | Makes the radio send a zero-hop advert, or a flood advert with `flood`. |

Command names are case-insensitive. Everything after the command name is
passed through as typed.

Notification emails have the subject
`You have received a MeshCore message from: <sender>`, the message text as the
body, and a fixed disclaimer that replies are not relayed back to the mesh.

Example `wx` reply:

```
33101 ALERT: Rip Current Statement | Mostly Cloudy, 20% precip 6h | 82F E14mph G18
```

(`G18` is wind gusts in mph.)

### Permissions

Senders are identified by the 6-byte public key prefix (12 hex characters)
MeshCore includes with every direct message. The console prints it for each
message, e.g. `[a1b2c3d4e5f6 Alice] wx 10001`.

- **public** commands can be run by anyone.
- **user** commands need a `[users.<prefix>]` section in the config.
- **admin** commands need the prefix in `[admin] keys`.

The user and admin lists are independent. Anything else — an unknown command,
or a command the sender isn't allowed to run — gets the reply
`unrecognized user or function`, at most once per sender every 5 minutes so
the bot can't be pulled into a reply loop with another automated node.

Senders must be in the radio's contacts, since direct messages from unknown
nodes can't be decrypted or replied to.

## Requirements

- Python 3.11+
- A MeshCore companion radio on USB serial
- The `mail` command (e.g. s-nail or mailutils) able to send through an SMTP
  server, for the `notify_*` commands
- Internet access for `wx` ([api.weather.gov](https://www.weather.gov/documentation/services-web-api)
  and [zippopotam.us](https://zippopotam.us) for zipcode lookup; no API keys)

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.toml config.toml   # then edit it
```

### Configuration

`config.toml` is git-ignored because it holds real email addresses and node
keys. See `config.example.toml`:

```toml
[admin]
keys = ["a1b2c3d4e5f6"]

[users.a1b2c3d4e5f6]
name = "Alice"  # for reference only
notify_default = "someone@example.com"
notify_group = ["someone@example.com", "someone.else@example.com"]
```

Each user's `notify_default` / `notify_group` may be a single address or a
list. A user with no addresses can still use `notify_email`.

### Email

Mail is sent by running `mail -s <subject> <addresses...>`, so `mail` must be
configured to deliver through an SMTP server. With s-nail and Gmail (using an
[app password](https://support.google.com/accounts/answer/185833)), for
example, in `~/.mailrc`:

```
set mta=smtps://you%40gmail.com:APP_PASSWORD@smtp.gmail.com:465
set from="you@gmail.com"
```

Keep SMTP credentials in your mail client's config, never in this repository.
Test with `echo test | mail -s test you@example.com` before relying on it.

## Running

```sh
.venv/bin/python listener.py              # auto-detects the serial port
.venv/bin/python listener.py -p /dev/ttyUSB0 -c /path/to/config.toml
```

Options: `-p/--port`, `-b/--baud` (default 115200), `-c/--config`
(default `config.toml` next to `listener.py`), `--debug` for library logging.

At startup it prints which commands are available at each permission level and
warns about any that are disabled for lack of configuration. Each reply is
retried until the radio reports an ack, and the console notes whether it was
delivered.

## Project layout

```
listener.py           radio connection, permission checks, dispatch, replies
weather.py            api.weather.gov / zipcode lookups (data only)
commands/
  __init__.py         command registry and config loading
  base.py             Command base class, permission levels, reply fitting
  wx.py               wx
  notify_default.py   notify_default and the shared email sending
  notify_group.py     notify_group
  notify_email.py     notify_email (validates the address from the mesh)
  advert.py           advert
config.example.toml   example configuration
```

### Adding a command

Create a `Command` subclass in its own module under `commands/` with `name`,
`usage`, `permission` (`PUBLIC`, `USER` or `ADMIN`) and an async
`execute(text, sender)` that returns a `CommandResult(console=..., reply=...)`.
Raise `CommandError` for failures whose message is safe to send back. Then add
an instance in `build_commands()` in `commands/__init__.py`.

## Security notes

- Commands never pass mesh text to a shell. Email goes to `mail` as argument
  and stdin; addresses typed into `notify_email` are strictly validated, and
  control characters are stripped from subjects.
- Anyone in `[users]` can email any address with `notify_email`; only add
  people you trust.
- A flood `advert` is sent to the whole mesh; use it sparingly.

## License

[MIT](LICENSE) © 2026 Doug Snitker
