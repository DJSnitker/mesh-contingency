# mesh-commands

Direct-message commands for [MeshCore](https://github.com/meshcore-dev/MeshCore)
bots. You write a command as a class or a function and turn it on in a
`[commands]` config table. The library takes care of the rest:

- who may run each command (`public`, `user`, `admin` or `disabled`)
- per-sender rate limits
- a time limit on each command
- fitting replies into 133-character mesh messages
- suggesting the nearest command name for a typo

`MeshLink` connects all of this to a radio through the
[`meshcore`](https://pypi.org/project/meshcore/) package.

It was cut out of [Mesh Contingency](../../README.md) and has no imports
from it, so the folder can be lifted into another project as is, or split
into its own repo with its history:
`git subtree split --prefix packages/mesh-commands`.

```sh
pip install ./packages/mesh-commands     # or -e for an editable install
```

## A bot in 20 lines

```python
import asyncio, tomllib
from meshcore import MeshCore
from mesh_commands import Dispatcher, KeyRoles, MeshLink, Registry

async def main():
    with open("config.toml", "rb") as f:
        config = tomllib.load(f)
    registry = Registry(config, group="my_bot.commands")   # entry point group for installed commands
    for warning in registry.warnings:
        print("Warning:", warning)
    mc = await MeshCore.create_serial("/dev/ttyUSB0", 115200, auto_reconnect=True)
    await mc.ensure_contacts()
    mc.auto_update_contacts = True
    roles = KeyRoles(admins=config.get("admins", {}).get("keys", []))
    link = MeshLink(mc, roles)
    commands = registry.build(mc, roles, send=link.send_later)
    link.listen(Dispatcher(commands, roles, link.send, registry.disabled))
    await mc.start_auto_message_fetching()
    await asyncio.Event().wait()

asyncio.run(main())
```

Only direct messages are handled. A message carries only the sender's
6-byte key prefix, so `MeshLink` matches it to the one radio contact with
that prefix for the full public key that permissions check. If none or
several contacts have it, the sender is unidentified and may only run
public commands. A radio with a copied prefix never gets anyone's rights.

## Writing a command

```python
from mesh_commands import Command, CommandError, CommandResult, command

@command(args="[NdS]", summary="Roll dice, e.g. 2d6")
def roll(text, sender, ctx):
    ...
    return f"{sender.name} rolled {total}"

class TideCommand(Command):
    args = "<station>"
    summary = "Today's tides"

    async def start(self):          # optional: once, after the radio connects
        return "tide: ready"        # a line for the project to print, or None

    async def execute(self, text, sender):
        if not text:
            raise CommandError(f"usage: {self.usage}")
        ...
        return CommandResult(console=full_report, reply=short_text)
```

**What a command gets**
- `text`: everything after its name.
- `sender`: a `Sender`, with `name` and `public_key`. The key is the full 64 hex characters, or `None` if the sender couldn't be identified.
- `ctx`, a `Context`, which holds:
  - `options`: the command's own config keys
  - `radio`
  - `commands`: every loaded command
  - `send(key, text)`: queue a direct message
  - `roles`
  - `extras`: one dict, the same for every command, for whatever the project passes in

**What a command returns**
- Reply text.
- A list of messages.
- A `CommandResult`.
- `None`, for no reply.

A long reply is split into numbered messages: at most 8, of 133 characters each.

**Errors**
- `raise CommandError("...")` sends that message back.
- Any other exception is answered with `<name>: failed`.
- A command that runs past its time limit is answered with `<name>: timed out`.

Sync functions run in a thread, so they can't hold up the radio.

**Helpers for fitting replies**
- `fit_reply`: one line, made of sections in priority order.
- `split_reply`: numbered parts.
- `pack`: as few messages as possible.
- `page`: page *n* of a long list.

`Confirmations` asks before something that can't be undone: the command acts only when the same thing is sent twice within 5 minutes.

`mesh_commands.builtin.help:HelpCommand` lists the commands the sender may
run, or shows how to use one. It never mentions a command the sender can't
run.

## The config

```toml
[commands]
help = { permission = "public" }
roll = { permission = "public", rate = "5/hour" }

[commands.tide]
handler = "my_bot.tide:TideCommand"   # module:attr, a Command subclass or function
permission = "user"
timeout = 20                           # seconds (default 60)
station = "8771450"                    # anything else is the command's own option

[limits]                               # default rates per level; these are the defaults
public_rate = "10/hour"
user_rate = "30/hour"
admin_rate = "none"
```

`Registry(config, group)` finds commands in two ways:
- installed packages, under the entry point group you name;
- `handler =` in a command's section.

It checks every section before anything connects. An unknown command, an unknown level, a bad handler or a bad timeout exits with a message saying which. Only enabled commands are imported, so installing a package never turns anything on. An installed command with no section is disabled, with a warning.

`retired=` names commands a project used to have: a config that still lists them gets one warning instead of an error.

## Permissions and rate limits

| Level | Who |
|---|---|
| `public` | anyone who can direct-message the node |
| `user` | senders `roles.is_user(key)` accepts |
| `admin` | senders `roles.is_admin(key)` accepts |
| `disabled` | nobody |

`KeyRoles(users=..., admins=...)` holds two sets of keys. Any object with
`is_user` and `is_admin` works instead, for example one that reads a users
file.

**Rate limits**
- They count per sender and command, over a sliding window.
- Past the limit, the sender is told once (`roll: limit reached, try again in 23 min`), then gets silence, so the limit can't make the node transmit.

**The `unrecognized user or function` reply**
- It answers unknown commands and commands the sender may not run, and the two look the same.
- It goes to each sender at most once per 5 minutes, so an auto-replying node can't trap the bot in a loop.
- Only senders who may run more than the public commands are told the nearest command name.

**What's printed**
- The sender's key prefix and name.
- The command's name.
- How the reply went.

Nobody's text or reply is printed. `mesh_commands.output.SafeOutput` escapes terminal control codes in everything printed, since names come from anyone on the mesh.

## Testing

```python
from mesh_commands import Sender
from mesh_commands.testing import FakeMeshCore, make_context

cmd = TideCommand(make_context("tide", options={"station": "x"}, radio=FakeMeshCore()))
result = await cmd.execute("today", Sender("Dana", "d0" * 32))
```

`FakeMeshCore` records what's asked of the radio and lets a test deliver
messages (`await radio.dm(prefix, text)`). The library's own tests use only
the standard library:

```sh
cd packages/mesh-commands && python -m unittest
```
