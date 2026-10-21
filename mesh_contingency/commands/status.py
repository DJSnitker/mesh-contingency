"""Check-ins: ok [status] records how the sender is doing, status <name or key>
looks it up, clearstatus empties the list.

Statuses are kept in status.json next to config.toml, so they survive a
restart, one per node.
"""

import re
import time

from ..api import Command, CommandError, CommandResult
from ..directory import unquote
from ..state import ago

FILENAME = "status.json"
DEFAULT_STATUS = "ok"
# A key prefix typed into status: at least 4 hex characters.
KEY_PREFIX_RE = re.compile(r"[0-9a-f]{4,64}")


class StatusBase(Command):
    """Commands that share the statuses in status.json."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.store = ctx.state.store(FILENAME)  # fails at startup if the file is unreadable

    @property
    def statuses(self):
        """{public key: {"name", "status", "time"}}"""
        return self.store.data


class OkCommand(StatusBase):
    args = "[status]"
    summary = "Check in: tell others you're ok, or how you are"

    async def execute(self, text, sender):
        if sender.public_key is None:
            raise CommandError(f"{self.name}: can't tell who you are; send an advert and try again")
        name = self.ctx.name_of(sender)
        status = text or DEFAULT_STATUS
        self.statuses[sender.public_key] = {"name": name, "status": status, "time": time.time()}
        self.store.save()
        return CommandResult(console=f"Status for {name}: {status}", reply=f"{self.name}: saved for {name}")


class StatusCommand(StatusBase):
    args = "<name or key>"
    summary = "Show someone's last check-in"

    def find(self, text):
        """Keys of the statuses whose name matches text (exactly, or else as
        part of the name), or else whose key starts with it. The name may be
        in « »."""
        quoted = unquote(text)
        wanted = (quoted[0] if quoted and not quoted[1] else text).lower()
        for match in (lambda key, entry: entry["name"].lower() == wanted,
                      lambda key, entry: wanted in entry["name"].lower(),
                      lambda key, entry: KEY_PREFIX_RE.fullmatch(wanted) and key.startswith(wanted)):
            keys = [key for key, entry in self.statuses.items() if match(key, entry)]
            if keys:
                return keys
        return []

    async def execute(self, text, sender):
        if not text:
            if sender.public_key not in self.statuses:
                raise CommandError(f"usage: {self.usage}")
            keys = [sender.public_key]
        else:
            keys = self.find(text)
        if not keys:
            raise CommandError(f"{self.name}: no status for {text}")
        names = [self.statuses[key]["name"] for key in keys]
        lines = []
        for key in sorted(keys, key=lambda k: -self.statuses[k]["time"]):
            entry = self.statuses[key]
            # The key prefix tells apart people with the same name.
            who = f"{entry['name']} ({key[:12]})" if names.count(entry["name"]) > 1 else entry["name"]
            lines.append(f"{who}: {entry['status']} ({ago(entry['time'])})")
        reply = "; ".join(lines)
        return CommandResult(console=reply, reply=reply)


class ClearStatusCommand(StatusBase):
    summary = "Delete every check-in"

    async def execute(self, text, sender):
        if text:
            raise CommandError(f"usage: {self.usage}")
        count = len(self.statuses)
        self.statuses.clear()
        self.store.save()
        reply = f"{self.name}: cleared {count} status{'' if count == 1 else 'es'}"
        self.ctx.state.record(self.ctx.name_of(sender), f"cleared {count} check-in(s)")
        return CommandResult(console=reply, reply=reply)
