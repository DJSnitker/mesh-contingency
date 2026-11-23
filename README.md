<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/branding/mesh-contingency-lockup.svg">
    <img src="docs/branding/mesh-contingency-lockup-dark.svg" alt="Mesh Contingency" width="560">
  </picture>
</p>

<p align="center">
  <strong>Weather alerts over MeshCore.</strong><br>
  National Weather Service alerts for your counties, posted to the mesh as they're issued.
</p>

<p align="center">
  <a href="https://github.com/DJSnitker/mesh-contingency/actions/workflows/ci.yml"><img src="https://github.com/DJSnitker/mesh-contingency/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-38BDF8?logo=python&logoColor=white" alt="Python 3.11+">
  <a href="https://github.com/meshcore-dev/MeshCore"><img src="https://img.shields.io/badge/radio-MeshCore-FF5F1F" alt="MeshCore"></a>
</p>

---

## About

A small bot for a [MeshCore](https://github.com/meshcore-dev/MeshCore)
companion radio connected over USB serial. It watches the National Weather
Service for the counties you list and posts each new alert to MeshCore's
Public channel, once, with nobody at the keyboard. Its admins can also post a
message there themselves (`alert`) and send the test message (`testalert`),
by direct message from their own radios.

Earlier versions did much more (users, a mailbox, email, check-ins, a web
console, phone and desktop apps). That's all kept on the git tag
`archive/full-system`; see [CHANGELOG.md](CHANGELOG.md) for what changed.

## Commands

The node answers direct messages from its admins (the radios in `[admins]`
in `config.toml`). Anyone else gets `unrecognized user or function`.

| Command | Who can run it (example config) | What it does |
|---|---|---|
| `alert <message>` | admins | Post a message to the Public channel |
| `help [command]` | admins | List the commands you can use, or show how to use one |
| `testalert` | admins | Post the test message to the Public channel now |

`alert` posts the message exactly as typed; it must fit in one channel
message (133 characters, less the node's name and ": ", which the radio puts
in front). An admin who mistypes a command is told the nearest one
(`unknown command alret; did you mean alert?`).

## Weather alerts

```toml
[alerts]
counties = ["Taylor, TX", "Jones, TX"]  # empty, the default, turns it off
every_minutes = 10                      # how often to check (at least 5)
severity = ["Extreme", "Severe"]        # optional: post only these
# events = ["Tornado Warning", "Flash Flood Warning"]  # optional: or only these
```

Write each county as its name and state (`"Taylor, TX"`; `Taylor County, TX`
works too). The bot looks up each county's NWS code once and keeps it in
`alerts.json` next to `config.toml`. Each round is then a single request for
the alerts in all the counties, including those the NWS issues for forecast
zones in them. Each alert is posted once, one message per alert, named by the
first watched county it covers:

```
Taylor, TX ALERT: Severe Thunderstorm Warning | until Tue 6:00PM | Taylor; Jones
```

An alert several counties share isn't repeated. What has been posted is kept
in `alerts.json` too, so a restart doesn't post anything again, and alerts
are forgotten some hours after they end. If something can't be looked up (no
internet, or api.weather.gov is down) the log says so once and the bot keeps
trying every round.

### What's posted

With no filter, every alert is posted. `severity` takes the NWS's levels
(Extreme, Severe, Moderate, Minor, Unknown) and `events` takes event names,
exactly as the NWS writes them but in any case. An alert is posted if it
passes every filter that's set. An alert filtered out is still remembered as
seen, so loosening the filter later doesn't post old alerts. The log says how
many each round left out.

### Where it's posted

Everything goes to MeshCore's Public channel, which every radio has. The bot
finds it by its key, which is the same on every radio, in whichever slot it's
in (usually 0). It never adds or renames a channel. If the radio has no
Public channel, nothing is posted:
- the bot warns at startup;
- `alert` and `testalert` say so;
- `install.sh --check` stops on it.

Before 1.0 the alerts went to a hashtag channel (`#contingency-wx`). A
`channel` setting left in `[alerts]` or `[commands.alert]` is ignored, with a
warning.

### Weekly test

So people know the alerts get through, the bot can post a test message every
week, followed by the counties it watches, and `testalert` posts it on
request:

```toml
[alert_test]
weekly = "Wednesday 17:00"     # or "Wed 5:00PM"; empty (the default) for no weekly test
timezone = "America/Chicago"   # defaults to the computer's time zone
# message = "TEST: this is a test of the weather alerts on this channel. No action needed."
```

The time is in the time zone given, daylight saving included. If the bot
isn't running at that time, that week's test is skipped, not sent late. The
message must fit in one channel message; the bot won't start if it doesn't.

## Requirements

- Linux (or another system with Python), with Python 3.11+
- A MeshCore companion radio on USB serial
- Internet access, for [api.weather.gov](https://www.weather.gov/documentation/services-web-api)
  (no API key)

## Setup

### One command

On Linux, as the user the node will run as. **Don't use sudo**: the node, its
files and its service all belong to that user (`curl … | sudo bash` is
refused).

```sh
curl -fsSL https://raw.githubusercontent.com/DJSnitker/mesh-contingency/main/install.sh | bash
```

A new install asks two questions first, so the rest runs without you:

- **Counties** for weather alerts, split by `;`, e.g. `Taylor, TX; Jones, TX`.
- **Your radio's public key**, to make it the first admin. Press Enter to
  skip; [The first admin](#the-first-admin) says where to find it.

Then it checks out the latest release into `~/mesh-contingency`, installs the
bot and its command library into a `.venv` there, and makes `config.toml`
from the example with your answers in it. It sets up the
[systemd user service](#as-a-service) without starting it. Last, it lists
what's left:
- anything you skipped;
- letting your user open the radio's USB port. With the radio plugged in, it
  tries the port itself and names the group to join.

The script never runs sudo itself. A few one-time steps need an admin of the
computer, so it prints those commands for you (or the computer's admin) to
run:

| When | Command it prints |
|---|---|
| git or Python 3.11+ with venv is missing (it stops) | e.g. `sudo apt-get install git python3 python3-venv` |
| Your user can't open the radio's USB port | `sudo usermod -aG dialout "$USER"` (the port's group), then log out and back in |
| The computer doesn't let users turn on lingering | `sudo loginctl enable-linger "$USER"`, so the node starts at boot with nobody logged in |

Once the radio is plugged in, check the node:

```sh
~/mesh-contingency/install.sh --check
```

It reads `config.toml` the way the bot does, then stops first if something
would keep the node from working:
- no radio, or a port you can't open;
- a mistake in the config;
- no counties.

It notes what the node runs without, which is no admins: `alert` and
`testalert` then answer no one. Then it starts the service, or restarts it,
and waits up to 90 seconds for the bot's `Listening for direct messages`. It
also stops if the radio has no Public channel, or if the alert watcher
didn't start. It shows any `Warning:` lines, or what the bot printed if it
stopped.

Run the install again to update: it moves to the newest release, reinstalls,
and restarts the service if it's running. Your config and saved data are
never overwritten, and an update asks nothing. Options go after
`bash -s --`:

| Option | What it does |
|---|---|
| `--counties "Taylor, TX; Jones, TX"` | Answers the counties question |
| `--admin-key KEY` | Answers the admin key question |
| `--dir DIR` | Installs somewhere else |
| `--ref main` | Follows `main` instead of the releases |
| `--no-service` | Skips the service |

### The first admin

The installer asks for it. To add one later, or more, put the radio's full
public key (64 hex characters; in the MeshCore app, share your contact to
see it) in `config.toml`:

```toml
[admins]
keys = ["<your 64-character key>"]
```

Other admins are more keys in the list. Restart the bot after a change. Then
advert from your radio, advert the node
(`systemctl --user kill --kill-whom=main -s USR1 mesh-contingency`), and send
it `help`.

The bot replies only to radios in its radio's contacts. A radio in
manual-add mode (a setting stored on the radio, which older versions of this
bot turned on) adds no one by itself; the bot then adds the admins' radios
when they advert, and nobody else.

Before 1.0 the admins were in `users.toml` (`[admin] keys`). If
`config.toml` has no `[admins]`, the bot still reads them from there, with a
warning to move them.

### By hand

```sh
python3 -m venv .venv
.venv/bin/pip install -e packages/mesh-commands -e .   # the command library, then the bot
cp config.example.toml config.toml   # then edit it
chmod 600 config.toml                # whoever can change it chooses the admins
```

### Configuration

Everything is in `config.toml`, read when the bot starts; see
`config.example.toml`. Who may run each command:

```toml
[commands]
help = { permission = "admin" }
alert = { permission = "admin" }
testalert = { permission = "admin" }
```

A permission is `"admin"` (the radios in `[admins]`), `"public"` (anyone who
can direct-message the node) or `"disabled"`. Optional per command:
`timeout = <seconds>` (default 60), `rate = "5/hour"`.

`[limits]` sets how often one sender may use each command, by permission
level (`public_rate = "10/hour"`, `admin_rate = "none"`, the defaults).

A config from an older version still starts: sections and commands that no
longer exist are ignored, with a warning that lists them.

## Running

```sh
.venv/bin/mesh-contingency              # auto-detects the serial port
.venv/bin/mesh-contingency -p /dev/ttyUSB0 -c /path/to/config.toml
```

Options: `-p/--port`, `-b/--baud` (default 115200), `-c/--config` (default
`config.toml` in the project folder), `--debug` for library logging.

### As a service

To start the bot at boot, restart it after a crash and keep its output in the
journal, run it as a systemd user service with
[`deploy/mesh-contingency.service`](deploy/mesh-contingency.service). The
[installer](#one-command) sets it up for you. By hand, from the project
folder:

```sh
mkdir -p ~/.config/systemd/user
sed "s|/path/to/mesh-contingency|$PWD|g" deploy/mesh-contingency.service \
    > ~/.config/systemd/user/mesh-contingency.service
loginctl enable-linger "$USER"     # start at boot without logging in
systemctl --user daemon-reload
systemctl --user enable --now mesh-contingency
journalctl --user -u mesh-contingency -f
```

`systemctl stop` (SIGTERM) shuts the bot down cleanly. If the radio is lost
and the library's reconnects fail, the bot logs `Lost the radio (...)` and
exits with an error, so systemd starts it again (every 30 s) until the radio
is back.

### The log

The bot prints only what happened, never what anyone wrote: the sender's key
prefix and name, the command's name, and how each reply went.

```
[adadadadadad Admin] alert
  -> running alert
  (reply to adadadadadad delivered)
  -> replied (32 chars)
```

### Adverts

Two radios can only exchange direct messages once each has the other as a
contact, which happens when each hears the other's advert. Without stopping
the bot:

- in its terminal, type `advert` (zero-hop), `advert flood`, or
  `contacts [name]` to check a radio has been added;
- from another shell, `kill -USR1 <pid>` sends a flood advert (as a service:
  `systemctl --user kill --kill-whom=main -s USR1 mesh-contingency`);
- or let it advert by itself:

  ```toml
  [advert]
  every_hours = 12     # advert this often (default 0, never)
  flood = true         # flood or zero-hop (default true)
  at_startup = false   # also advert every time the bot starts (default false)
  ```

  The next advert goes out 12 hours after the last one of that kind, kept in
  `adverts.json`, so a restart doesn't flood the mesh again.

## Writing a command

The commands run on [`mesh-commands`](packages/mesh-commands/README.md), a
library in this repo with no imports from Mesh Contingency, so it can be
lifted into another MeshCore bot. A command of your own is written against
it. You can name it in `config.toml` with `handler = "module:attr"`, or
register it from a package under the `mesh_contingency.commands` entry point
group:

```python
from mesh_commands import command

@command(args="[NdS]", summary="Roll dice, e.g. 2d6")
def roll(text, sender, ctx):
    ...
    return f"{sender.name} rolled {total}"
```

`ctx.extras["state"]` is the bot's saved state (the JSON files next to
`config.toml`). The library's README covers the rest: classes, replies,
errors, permissions and testing with its fake radio.

## Testing

```sh
.venv/bin/python -m unittest                                   # the bot
(cd packages/mesh-commands && ../../.venv/bin/python -m unittest)   # the library
.venv/bin/pip install -e ".[dev]" && .venv/bin/ruff check .   # lint
```

The tests use only the standard library. The network and the radio are
faked, so they run offline and without a device. `tests/test_bot.py` drives
the real `mesh_contingency.bot.main()` with simulated direct messages.

## Contributing

Pull requests run [CI](.github/workflows/ci.yml) on GitHub, and it must pass:
the tests on Python 3.11 to 3.14, the library's tests on their own, lint with
[ruff](https://docs.astral.sh/ruff/), a build and clean install of the wheel,
and the install script (shellcheck, a fresh install and an update). Never
include real data (your `config.toml`, node keys) in code, tests or issues.

## Project layout

```
mesh_contingency/
  bot.py              entry point: the radio, the alert tasks, adverts; DMs go to mesh_commands
  config.py           reading config.toml: the admins, the commands, settings older versions had
  alerts.py           posting to Public; the automatic weather alerts, their filter, the weekly test
  weather.py          api.weather.gov: county codes and active alerts
  contacts.py         adding the admins' radios; listing contacts
  console.py          commands typed into the bot's terminal, scheduled adverts
  state.py            the JSON files kept next to config.toml
  commands/           alert and testalert
packages/mesh-commands/
  mesh_commands/      the command library: commands, permissions, rate limits,
                      the registry, dispatching DMs, the MeshCore link, help, test fakes
  tests/              its own tests (run from that folder)
deploy/               the systemd user unit
install.sh            the one-command installer
docs/plans/           design plans and what was decided
tests/                the bot's tests (python -m unittest)
```

## Security notes

- Whoever can change `config.toml` chooses the admins: keep it writable only
  by you (`chmod 600`); the bot warns at startup if it isn't.
- An admin is matched by the full public key of a contact in the radio. A
  message carries only a key prefix, so if two contacts share an admin's
  prefix neither gets admin rights, and the log says to remove the impostor.
- `alert` and the weather alerts post to the Public channel, which every
  radio in range can read.
- Everything the bot prints has terminal control sequences escaped, since
  names come from anyone on the mesh.
- `meshcore` is held to the tested minor version, and CI's GitHub Actions are
  pinned to commit SHAs; Dependabot proposes updates to both.

## License

Proprietary. © 2026 Doug Snitker, all rights reserved; see [LICENSE](LICENSE).
