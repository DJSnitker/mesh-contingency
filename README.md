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
nodes can't be decrypted or replied to. See [Contacts](#contacts) for adding
them automatically.

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
.venv/bin/pip install -e .           # installs meshcore and the mesh-contingency command
cp config.example.toml config.toml   # then edit it
```

The editable install (`-e`) runs the code straight from this folder, so edits
take effect on restart and `config.toml` here is found by default.

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

### Contacts

By default a MeshCore radio stores every node whose advert it hears, so
repeaters, room servers and sensors can fill its contact table and block new
people from messaging the bot. With a `[contacts]` section the bot takes
over instead:

```toml
[contacts]
auto_add = ["chat"]   # any of: chat, repeater, room, sensor; [] adds none
```

At startup it puts the radio in manual-add mode (`manual_add_contacts`, a
setting stored on the radio that also affects the phone app), then adds each
newly heard node whose type is listed, logging e.g.
`+ contact a1b2c3d4e5f6 Alice (chat)`. Nodes heard while the bot isn't
running are picked up when they advert again. Without a `[contacts]` section
the radio's setting is left as it is.

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
.venv/bin/mesh-contingency              # auto-detects the serial port
.venv/bin/mesh-contingency -p /dev/ttyUSB0 -c /path/to/config.toml
```

With the venv activated (`source .venv/bin/activate`), plain
`mesh-contingency` works. `python mesh_contingency.py` still works without
installing.

Options: `-p/--port`, `-b/--baud` (default 115200), `-c/--config`
(default `config.toml` next to `mesh_contingency.py`), `--debug` for library logging.

At startup it prints which commands are available at each permission level and
warns about any that are disabled for lack of configuration. Each reply is
retried until the radio reports an ack, and the console notes whether it was
delivered.

## Testing

```sh
.venv/bin/python -m unittest
```

The tests use only the standard library. Network calls, the `mail` command
and the radio are all faked (see `tests/fakes.py`), so they run offline and
without a device. `tests/test_mesh_contingency.py` drives the real `mesh_contingency.main()`
with simulated direct messages.

## Project layout

```
mesh_contingency.py   entry point: radio connection, permissions, dispatch, replies
contacts.py           auto-adding new contacts by node type
weather.py            api.weather.gov / zipcode lookups (data only)
commands/
  __init__.py         command registry and config loading
  base.py             Command base class, permission levels, reply fitting
  wx.py               wx
  notify_default.py   notify_default and the shared email sending
  notify_group.py     notify_group
  notify_email.py     notify_email (validates the address from the mesh)
  advert.py           advert
pyproject.toml        package metadata and the mesh-contingency command
config.example.toml   example configuration
tests/                unit tests (python -m unittest)
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
