# mesh-contingency

[![CI](https://github.com/DJSnitker/mesh-contingency/actions/workflows/ci.yml/badge.svg)](https://github.com/DJSnitker/mesh-contingency/actions/workflows/ci.yml)

A small bot for a [MeshCore](https://github.com/meshcore-dev/MeshCore) companion
radio connected over USB serial. It listens for **direct messages** sent to the
radio, runs simple commands, and replies over the mesh. It is meant as a
contingency link: someone with only a mesh radio can check the weather, read
a Bible verse, or get a message out by email. Commands are plugins: anyone can
write one in a separate package and install it (see
[Writing a command](#writing-a-command)).

Channel messages are ignored entirely; only direct messages are acted on.

## Commands

| Command | Who can run it (example config) | What it does |
|---|---|---|
| `help [command]` | anyone | Lists the commands the sender may run, or shows how to use one. Commands the sender can't run aren't mentioned. |
| `wx <zipcode>` | anyone | Current conditions, chance of precipitation and active NWS alerts for a US zipcode. Full report on the console; a ≤133-char summary is sent back, prioritizing alerts, then precipitation, then temperature and wind. |
| `verse [reference]` | anyone | A Bible verse or short passage from the Berean Standard Bible, e.g. `verse john 3:16` or `verse ps 23:1-3`; plain `verse` gives the verse of the day. Works offline. |
| `quickim <message>` | users | Emails the message to the sender's preset contact. |
| `emailall <message>` | users | Emails the message to the sender's preset group of addresses. |
| `email <address> <message>` | users | Emails the message to the given address. |
| `advert [flood]` | admins | Makes the radio send a zero-hop advert, or a flood advert with `flood`. |
| `reload` | admins | Reads the [users file](#users-file) now and replies with what changed. |

Command names are case-insensitive. Everything after the command name is
passed through as typed. Replies too long for one 133-character message are
split into numbered messages (`(1/3) ...`), at most 8 per reply.

Notification emails have the subject
`You have received a MeshCore message from: <sender>`, the message text as the
body, and a fixed disclaimer that replies are not relayed back to the mesh.

Example `wx` reply:

```
33101 ALERT: Rip Current Statement | Mostly Cloudy, 20% precip 6h | 82F E14mph G18
```

(`G18` is wind gusts in mph.)

### Bible verses

The whole [Berean Standard Bible](https://berean.bible/) is bundled with the
bot (`mesh_contingency/bible/bsb.json.gz`, 1.2 MB), so `verse` never touches the network. The
BSB was dedicated to the public domain in 2023, so verses are sent without a
copyright notice.

References accept full book names, standard abbreviations and any
unambiguous prefix: `john 3:16`, `jn 3:16`, `1 jn 4:8`, `I John 4:8`,
`song 2:4`, `phil 4:13`. Single-chapter books can be cited by verse alone
(`jude 24`). A range within one chapter, `ps 23:1-3`, numbers each verse
after the first.

A reply that doesn't fit in one 133-character message is split between words
into numbered messages, so they can be read in order even if the mesh
delivers them out of sequence:

```
(1/2) John 3:16 For God so loved the world that He gave His one and only Son, that everyone who believes in Him shall not perish but
(2/2) have eternal life.
```

A reply may take at most 8 messages; longer ranges are refused. The verse of
the day comes from a built-in list of 237 well-known verses
(`mesh_contingency/bible/votd.py`), taken in turn by date, so everyone gets the same verse on
the same day. Text is converted to plain ASCII (straight quotes, `--` for
dashes). Verses the BSB omits from the main text, such as Matthew 17:21, are
reported as not in the text.

The bundled file is built from the [Free Use Bible API](https://bible.helloao.org)
with `python -m mesh_contingency.bible.build`. It only needs rebuilding to pick up corrections
to the source text.

### Permissions

Users and admins are listed by their full public key (64 hex characters),
which the MeshCore app shows for your node. A direct message carries only the
first 12 characters (the prefix), so the bot looks the sender up in the
radio's contacts and checks that contact's full key against the
[users file](#users-file). If no
contact, or more than one, has the prefix, the sender is unidentified and may
only run public commands, so a node that copies someone's prefix never gets
their rights. The console prints the prefix and name for each message, e.g.
`[a1b2c3d4e5f6 Alice] wx 10001`.

Who may run each command is set entirely in the config's `[commands]`
table (see [Configuration](#configuration)); the code has no built-in levels.
Each command gets one of:

- **public**: anyone.
- **user**: senders with a `[users.<public key>]` section in the users file.
- **admin**: senders whose public key is in the users file's `[admin] keys`.
- **disabled**: nobody.

An installed command with no entry is disabled, with a warning at startup,
so installing a command never opens it until you allow it. An unknown
command name or level stops the bot before it connects.

The user and admin lists are independent: an admin isn't automatically a
user. Anything else — an unknown command,
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
  server, for the `quickim`, `emailall` and `email` commands
- Internet access for `wx` ([api.weather.gov](https://www.weather.gov/documentation/services-web-api)
  and [zippopotam.us](https://zippopotam.us) for zipcode lookup; no API keys).
  `verse` works offline.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -e .           # installs meshcore and the mesh-contingency command
cp config.example.toml config.toml   # then edit it
cp users.example.toml users.toml     # then add your users and admins
chmod 600 config.toml users.toml     # they hold email addresses and keys
```

The editable install (`-e`) runs the code straight from this folder, so edits
take effect on restart, and `config.toml` and `users.toml` here are found by
default. Re-run the install after pulling changes that add modules or
commands, since commands are registered when the package is installed.

### Configuration

`config.toml` holds the settings that change rarely and are read at startup:
commands, permissions and contacts. People go in the [users file](#users-file),
which can change while the bot runs. Both are git-ignored because they hold
real email addresses and node keys. See `config.example.toml`:

```toml
[commands]
help = { permission = "public" }
wx = { permission = "public" }
verse = { permission = "public" }
quickim = { permission = "user" }
emailall = { permission = "user" }
email = { permission = "user" }
advert = { permission = "admin" }
reload = { permission = "admin" }
```

Each entry under `[commands]` takes:

| Key | Meaning |
|---|---|
| `permission` | Required: `public`, `user`, `admin` or `disabled`. |
| `timeout` | Seconds before the command is abandoned with a "timed out" reply (default 60). |
| `handler` | Code to run, as `"module:attr"`: a `Command` subclass or a function. Only needed for commands that aren't installed as a package, or to run installed code under another name. |
| anything else | Passed to the command as its options. |

A command with options reads more easily as its own section:

```toml
[commands.roll]
permission = "public"
max_dice = 10
```

The same code can run under several names. For example, a second quickim
command whose addresses come from each user's `quickfam` key:

```toml
[commands.quickfam]
handler = "mesh_contingency.commands.quickim:QuickImCommand"
permission = "user"
```

Each user's `quickim` / `emailall` key may be a single address or a list.
A user with no addresses can still use `email`. A `quickim` or `emailall`
message that starts with an email address is refused with a pointer to
`email`, so a message meant for someone else isn't sent to the preset
contact by mistake.

### Users file

Users and admins are in `users.toml`, next to `config.toml` (see
`users.example.toml`):

```toml
[admin]
keys = ["a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"]

[users.a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2]
name = "Alice"  # used in reload messages
quickim = "someone@example.com"
emailall = ["someone@example.com", "someone.else@example.com"]
```

Keys are full public keys (64 hex characters); the 12-character prefix is not
accepted. Each user's settings are read by the commands: `quickim` and
`emailall` take one address or a list.

The bot checks the file every 5 seconds and applies changes without a restart,
logging what changed, e.g. `users.toml reloaded: added Bob; changed Alice`. A
change is used once the file has stopped changing, so it takes effect within
about 10 seconds. To apply it at once, send `reload` as an admin or signal the
bot with `kill -HUP <pid>`.

If an edit is invalid (bad TOML, a short key, a misspelled section), the bot
keeps the users it has, logs the reason and sends it to each admin, e.g.
`users.toml not reloaded: [users]: 'a1b2c3' is not a full public key`. Fix the
file and it is picked up on the next check. A deleted file is reported the
same way. At startup, an invalid file stops the bot; a missing one only
warns, and is picked up once created.

To use another file or interval, add to `config.toml`:

```toml
[directory]
file = "/etc/mesh-contingency/users.toml"   # relative paths are relative to config.toml
reload_seconds = 5                          # 0 = only on reload or SIGHUP
```

Users and admins used to be in `config.toml`; the bot now stops with a message
if they are still there.

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

Each admin also gets a direct message for every contact added, e.g.
`New contact: Alice (a1b2c3d4e5f6, chat)`, so they know who has appeared and
can ask for the person's full public key to add them to the users file. Set
`notify_admins = false` under `[contacts]` to turn this off. Admins must
themselves be contacts to receive it. Notices are sent in the background, one
message at a time, so they never hold up replies to incoming messages.

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
`mesh-contingency` works, as does `python -m mesh_contingency`.

Options: `-p/--port`, `-b/--baud` (default 115200), `-c/--config`
(default `config.toml` in the project folder), `--debug` for library logging.

At startup it checks the config and loads the enabled commands before
connecting, prints which commands are available at each permission level, and
warns about any that are disabled or failed to load. It then watches the
users file (see [Users file](#users-file)). Each command has a time
limit (60 s unless its config says otherwise). Each reply is
retried until the radio reports an ack, and the console notes whether it was
delivered.

## Testing

```sh
.venv/bin/python -m unittest
.venv/bin/pip install -e ".[dev]" && .venv/bin/ruff check .   # lint
```

The tests use only the standard library. Network calls, the `mail` command
and the radio are all faked (see `mesh_contingency/testing.py`), so they run
offline and without a device. `tests/test_bot.py` drives the real
`mesh_contingency.bot.main()` with simulated direct messages.

## Contributing

Pull requests run [CI](.github/workflows/ci.yml) on GitHub, and it must pass:

- **Tests** on Python 3.11, 3.12, 3.13 and 3.14.
- **Lint** with [ruff](https://docs.astral.sh/ruff/); the rules are in `pyproject.toml`.
- **Package**: builds the wheel, checks the Bible data and command
  registrations are inside it, installs it with `examples/mesh-dice`, and runs
  a verse lookup and a dice roll through the installed commands.

The PR template has a short checklist. Never include real data (your
`config.toml` or `users.toml`, email addresses, node keys) in code, tests or issues.
Dependabot opens weekly PRs to update GitHub Actions and Python dependencies.

## Project layout

```
mesh_contingency/
  api.py              the interface for commands: Command, Context, CommandResult, reply limits
  registry.py         finding commands (entry points), checking [commands], loading them
  directory.py        the users file: checking it and reloading it while running
  bot.py              entry point: radio connection, permissions, dispatch, replies
  testing.py          fake radio and make_context() for testing commands
  contacts.py         auto-adding new contacts by node type
  weather.py          api.weather.gov / zipcode lookups (data only)
  bible/
    __init__.py       reference parsing and verse lookup
    bsb.json.gz       the bundled Berean Standard Bible
    build.py          rebuilds bsb.json.gz
    votd.py           verse-of-the-day list
  commands/           built-in commands, one module each
    help.py, wx.py, verse.py, advert.py, reload.py
    mail.py           the shared email sending and address checks
    quickim.py, emailall.py, email.py
examples/mesh-dice/   an example third-party command package
.github/              CI workflow, Dependabot, PR and issue templates
pyproject.toml        package metadata, the mesh-contingency command and built-in command registrations
config.example.toml   example configuration
users.example.toml    example users file
tests/                unit tests (python -m unittest)
```

## Writing a command

A command is a Python class or function. It can live in its own package,
installed next to the bot, so you never edit this project.
`examples/mesh-dice` is a complete example.

### As a function

```python
from mesh_contingency.api import CommandError, command

@command(args="[NdS]", summary="Roll dice, e.g. 2d6")
def roll(text, sender, ctx):
    ...
    return f"{sender.name} rolled {total}"
```

The function gets the text after the command name, the `Sender` (`name` and
`public_key`, the full 64-hex key, or `None` if the sender couldn't be
identified) and the `Context`. It returns the reply text.
It can be `async def`; a plain `def` runs in a worker thread so it can't stall
the radio.

### As a class

```python
from mesh_contingency.api import Command, CommandError, CommandResult

class TideCommand(Command):
    args = "<station>"
    summary = "Today's tides"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.default = ctx.options.get("station")

    async def execute(self, text, sender):
        ...
        return CommandResult(console=full_report, reply=short_text)
```

Use a class when the command keeps state or needs setup.

### What a command gets and returns

`ctx` (a `Context`) holds:
- `name`: the name the command answers to
- `options`: the extra keys from its config entry
- `users`: each user's `[users.<key>]` settings from the users file, by public key
- `admins`: the admins' public keys
- `directory`: the users file itself

`users` and `admins` change when the users file is reloaded, so read them
when the command runs instead of keeping a copy from `__init__`.
- `radio`: the connected `meshcore.MeshCore`
- `commands`: every loaded command
- `allowed(command, sender)`

A command returns reply text, a list of messages, a `CommandResult(console=...,
reply=...)` or `None` for no reply. The bot enforces the mesh limits for every
command:
- text is split into numbered messages;
- each reply is capped at 8 messages, and each message at 133 characters;
- each command has a time limit.

To fail, raise `CommandError("...")` with a short message to send back. Any
other exception is logged and answered with `<name>: failed`, so error details
never leak onto the mesh.

### Registering it

In your package's `pyproject.toml`, the name on the left is the command name:

```toml
[project.entry-points."mesh_contingency.commands"]
roll = "mesh_dice:roll"
flip = "mesh_dice:FlipCommand"
```

Install it into the bot's environment (`.venv/bin/pip install ./mesh-dice`
or from PyPI) and add an entry for it under `[commands]` in `config.toml`.
Without installing, `handler = "module:attr"` in that entry works too, as long
as the module is importable (e.g. on `PYTHONPATH`).

The built-in commands are registered the same way, in this project's
`pyproject.toml`. If two installed packages offer the same command name, the
bot stops at startup; pick one with `handler`.

### Testing it

```python
from mesh_contingency.api import Sender
from mesh_contingency.testing import FakeMeshCore, make_context

cmd = TideCommand(make_context("tide", options={"station": "8724580"}, radio=FakeMeshCore()))
result = await cmd.execute("", Sender("Dana", "d0" * 32))
```

## Security notes

- Commands never pass mesh text to a shell. Email goes to `mail` as argument
  and stdin; addresses typed into `email` are strictly validated, and
  control characters are stripped from subjects.
- Anyone in the users file can email any address with `email` while it is
  a `user` command; only add people you trust.
- Think before making a command `public`: anyone on the mesh who can reach
  the node could run it. The email commands and `advert` act outside the bot.
- Installed commands run inside the bot with all of its access (radio,
  network, `mail`, files). Permissions only decide who on the mesh may
  trigger them. Install only command packages you trust. Disabled commands
  are never imported.
- A flood `advert` is sent to the whole mesh; use it sparingly.
- The users file decides who is an admin, and changes to it apply while the
  bot runs. Keep it writable only by you (`chmod 600 users.toml`).

## License

[MIT](LICENSE) © 2026 Doug Snitker
