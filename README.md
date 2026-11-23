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


## What it does

A small bot for a [MeshCore](https://github.com/meshcore-dev/MeshCore)
companion radio on a Linux computer's USB port:
- Every 10 minutes it asks the National Weather Service about the counties
  you list.
- It posts each new alert to MeshCore's **Public channel** (or one you pick), once:
  ```
  Taylor, TX ALERT: Severe Thunderstorm Warning | until Tue 6:00PM | Taylor; Jones
  ```
- Its admins can post there themselves, and test it, by direct message from
  their own radios.

Earlier versions did much more: users, a mailbox, email, check-ins, a web
console, and phone and desktop apps. All of it is kept on the git tag
`archive/full-system`; [CHANGELOG.md](CHANGELOG.md) lists what went.

## Install

On Linux, as the user the node will run as. **Not with sudo**: the node, its
files and its service belong to that user.

```sh
curl -fsSL https://raw.githubusercontent.com/DJSnitker/mesh-contingency/main/install.sh | bash
```

It asks two questions, then installs everything without you:
- **counties**, e.g. `Taylor, TX; Jones, TX`;
- **your radio's public key**, to be the first admin (64 hex digits; in the
  MeshCore app, share your contact to see it). Enter skips it.

What it sets up:
- the latest release in `~/mesh-contingency`, with the bot in a `.venv`;
- `config.toml`, with your answers;
- a systemd user service, so the bot starts at boot.

It never runs sudo. When a one-time step needs the computer's admin, it
prints the command to run instead:

| When | Command it prints |
|---|---|
| git or Python 3.11+ is missing | e.g. `sudo apt-get install git python3 python3-venv` |
| You can't open the radio's USB port | `sudo usermod -aG dialout "$USER"`, then log out and back in |
| Users can't turn on lingering | `sudo loginctl enable-linger "$USER"` |

Options go after `bash -s --`:

| Option | What it does |
|---|---|
| `--counties "Taylor, TX; Jones, TX"` | Answers the counties question |
| `--admin-key KEY` | Answers the admin key question |
| `--dir DIR` | Installs somewhere else |
| `--ref main` | Follows `main` instead of the releases |
| `--no-service` | Skips the service |

## Check it

Plug in the radio, then:

```sh
~/mesh-contingency/install.sh --check
```

**Before starting, it stops on:**
- no radio, or a USB port you can't open;
- a mistake in `config.toml`;
- no counties.

It also notes when there are no admins.

**Then** it starts (or restarts) the service and waits for the bot to say
it's listening. It also stops if the radio has no alert channel, or if the
alert watcher didn't start, and it shows any `Warning:` the bot printed.

Then, from an admin's radio:
1. Advert, so the node learns your radio.
2. Send the node `help`.
3. Send `testalert`: the test message should arrive on the channel.

## Configure

Everything is in `config.toml`, read when the bot starts. Restart after a
change with `systemctl --user restart mesh-contingency`.
[`config.example.toml`](config.example.toml) has every setting.

```toml
[alerts]
counties = ["Taylor, TX", "Jones, TX"]
every_minutes = 10                  # at least 5
# channel = "#wx-test"              # instead of Public, e.g. to try it out
severity = ["Extreme", "Severe"]    # optional filter
# events = ["Tornado Warning", "Flash Flood Warning"]

[alert_test]
weekly = "Wednesday 17:00"          # or "Wed 5:00PM"; leave out for none
timezone = "America/Chicago"

[admins]
keys = ["<64-hex public key>"]

[advert]
every_hours = 12                    # so radios can find the node
```

**Alerts.**
- Each county is a name and state; `Taylor County, TX` works too.
- An alert several counties share is posted once, named by the first county
  it covers.
- What has been posted is kept in `alerts.json`, so a restart doesn't repeat
  anything.

**The filter.**
- With no filter, every alert is posted.
- `severity` takes the NWS's levels: Extreme, Severe, Moderate, Minor, Unknown.
- `events` takes event names, in any case.
- An alert must pass every filter you set.
- An alert that's filtered out is still remembered, so changing the filter
  doesn't post old ones.

**The channel.**
- Everything goes to Public unless `channel` names a hashtag channel, such
  as `"#wx-test"` (the `#` is optional). Use one to try the node out
  without posting to everyone: join the same channel on your own radio.
- The bot finds the channel by its key, in whatever slot it's in. Public's
  key is the same on every radio; a hashtag channel's comes from its name.
- A hashtag channel the radio doesn't have is added to its first empty slot.
  Public is never added or changed.
- Anyone in range reads what's posted to Public, and anyone who knows a
  hashtag channel's name can join it.

**The weekly test** posts a test message, then the counties watched. If the
bot isn't running at that time, that week's test is skipped.

**Admins** are radios' full public keys in `[admins] keys`. The bot replies
only to radios in its radio's contacts; on a radio in manual-add mode, it
adds the admins' radios when they advert, and nobody else.

## Commands

The node answers direct messages from its admins. Anyone else gets
`unrecognized user or function`.

| Command | Who can run it (example config) | What it does |
|---|---|---|
| `advert [zero]` | admins | Send a flood advert now, so radios can find the node (`zero`: only to radios in direct range) |
| `alert <message>` | admins | Post a message to the alert channel (Public unless set) |
| `help [command]` | admins | List the commands you can use, or show how to use one |
| `testalert` | admins | Post the test message to the alert channel now |

`alert` posts the message as typed. It must fit in one channel message: 133
characters, less the node's name and `: `. Who may run each command is set
in `[commands]`, as `admin`, `public` or `disabled`, with an optional
`rate = "5/hour"`; `[limits]` sets the defaults per level
(`public_rate = "10/hour"`, `admin_rate = "none"`).

```toml
[commands]
help = { permission = "admin" }
alert = { permission = "admin" }
testalert = { permission = "admin" }
advert = { permission = "admin" }
```

## Update

Run the install command again. It moves to the newest release, reinstalls,
and restarts the service if it's running. It never asks questions and never
touches your `config.toml` or saved data. A config from before 1.0 still
starts:
- settings that no longer exist are ignored, with a warning listing them;
- admins in an old `users.toml` are still read, with a warning to move them
  to `[admins]`.

## Troubleshoot

Everything the bot does is in its log, which shows names and command names
but never anyone's text:

```sh
journalctl --user -u mesh-contingency -f
```

| You see | What to do |
|---|---|
| `No serial device found` | Plug in the radio. The service tries again every 30 s. |
| `Lost the radio (...)` | The USB link dropped. The service reconnects once it's back. |
| `No Public channel on the radio` | Add MeshCore's Public channel back in the radio's app. |
| `no free channel slot on the radio for #...` | Delete a channel you don't use in the radio's app. |
| An admin gets `unrecognized user or function` | Check the key in `[admins]` is that radio's full key, then advert from it. |
| `couldn't check for alerts (...)` | No internet, or api.weather.gov is down. It tries again each round. |
| `N new alert(s) not posted (filtered out ...)` | That's the filter in `[alerts]` at work. |

To make the node advert now: send it `advert` from an admin radio, or run
`systemctl --user kill --kill-whom=main -s USR1 mesh-contingency` on its
computer.

To run it by hand instead of as a service, stop the service first:
`.venv/bin/mesh-contingency` finds the radio by itself; `-p /dev/ttyUSB0`,
`-c path/to/config.toml` and `--debug` are there if you need them.

## Uninstall

```sh
systemctl --user disable --now mesh-contingency
rm ~/.config/systemd/user/mesh-contingency.service
systemctl --user daemon-reload
rm -rf ~/mesh-contingency          # keep a copy of config.toml first if you want it
```

The radio keeps its own settings. If an older version put it in manual-add
mode, turn that off in the MeshCore app.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e packages/mesh-commands -e ".[dev]"
.venv/bin/python -m unittest                                        # the bot
(cd packages/mesh-commands && ../../.venv/bin/python -m unittest)   # the library
.venv/bin/ruff check .
```

The tests need no radio and no network.
[CI](.github/workflows/ci.yml) runs them on Python 3.11 to 3.14, along with:
- the library on its own;
- lint;
- a wheel install;
- the install script.

The commands run on [`mesh-commands`](packages/mesh-commands/README.md), a
library in this repo with no imports from Mesh Contingency. A command of
your own is written against it, then named in `config.toml` with
`handler = "module:attr"` or registered under the `mesh_contingency.commands`
entry point group. Its state is in `ctx.extras["state"]`.

**Security:**
- Keep `config.toml` writable only by you (`chmod 600`): whoever can change
  it chooses the admins. The bot warns if it isn't.
- Admins are matched by full public key. Two contacts sharing an admin's key
  prefix get no rights.
- Never put real keys in code, tests or issues.

## License

Proprietary. © 2026 Doug Snitker, all rights reserved; see [LICENSE](LICENSE).
