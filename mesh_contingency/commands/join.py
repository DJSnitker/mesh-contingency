"""Joining the users: join [name] asks, an admin answers with approve or deny.

Requests wait in requests.json next to config.toml. Approving adds the
person's section to the users file, which then reloads, and tells them.
"""

import re
import time

from ..api import Command, CommandError, CommandResult
from ..directory import DirectoryError
from ..names import check_name, name_problem, suggest
from ..state import ago

FILENAME = "requests.json"
# Requests waiting at most, so the admins can't be flooded.
MAX_REQUESTS = 20
# A key prefix naming a request: at least 4 hex characters.
KEY_PREFIX_RE = re.compile(r"[0-9a-f]{4,64}")


class RequestsBase(Command):
    """Commands that share the join requests in requests.json."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.store = ctx.state.store(FILENAME)  # fails at startup if the file is unreadable

    @property
    def requests(self):
        """{public key: {"name", "time"}}"""
        return self.store.data

    def find(self, text):
        """The key of the one request whose name is text, or whose key starts
        with it. Raises CommandError if none or several match."""
        wanted = text.strip().lower()
        keys = [k for k, r in self.requests.items() if r["name"].lower() == wanted]
        if not keys and KEY_PREFIX_RE.fullmatch(wanted):
            keys = [k for k in self.requests if k.startswith(wanted)]
        if not keys:
            raise CommandError(f"{self.name}: no request from {text}")
        if len(keys) > 1:
            raise CommandError(f"{self.name}: {len(keys)} requests match; use the key prefix: "
                               + ", ".join(k[:12] for k in keys))
        return keys[0]


class JoinCommand(RequestsBase):
    args = "[name]"
    summary = "Ask the admins to make you a user, under a one-word name"

    async def execute(self, text, sender):
        if sender.public_key is None:
            raise CommandError(f"{self.name}: can't tell who you are; send an advert and try again")
        if sender.public_key in self.ctx.users:
            raise CommandError(f"{self.name}: you're already a user")
        name = text.strip() or sender.name
        if not text.strip() and name_problem(name):
            hint = suggest(name)
            raise CommandError(f"{self.name}: your radio's name can't be used; send {self.name} <name>"
                               + (f", e.g. {self.name} {hint}" if hint else ""))
        check_name(self.name, name)
        key = sender.public_key
        new = key not in self.requests
        if new and len(self.requests) >= MAX_REQUESTS:
            raise CommandError(f"{self.name}: too many requests waiting; try again later")
        self.requests[key] = {"name": name, "time": time.time()}
        self.store.save()
        if new:
            self.ctx.tell_admins(f"Join request: {name} ({key[:12]}). Reply approve {key[:12]} or deny {key[:12]}")
        return CommandResult(console=f"Join request from {name} ({key[:12]})",
                             reply=f"{self.name}: request {'sent to the admins' if new else 'updated'}")


class ApproveCommand(RequestsBase):
    args = "[name or key]"
    summary = "Make someone who asked to join a user; alone, list the requests"

    async def execute(self, text, sender):
        if not text:
            if not self.requests:
                return CommandResult(console="", reply=f"{self.name}: no requests")
            pending = sorted(self.requests.items(), key=lambda kr: kr[1]["time"])
            reply = "requests: " + "; ".join(f"{r['name']} ({k[:12]}) {ago(r['time'])}" for k, r in pending)
            return CommandResult(console=reply, reply=reply)
        key = self.find(text)
        name = self.requests[key]["name"]
        directory = self.ctx.directory
        if key not in self.ctx.users:  # unless added by hand meanwhile
            try:
                directory.save_user(key, {"name": name})
            except DirectoryError as e:
                raise CommandError(f"{self.name}: {directory.name} {e}") from None
        del self.requests[key]
        self.store.save()
        self.ctx.send(key, f"Welcome, {name}: you're now a user. Send help for your commands.")
        return CommandResult(console=f"Approved {name} ({key[:12]}); added to {directory.name}",
                             reply=f"{self.name}: {name} added to {directory.name}")


class DenyCommand(RequestsBase):
    args = "<name or key>"
    summary = "Turn down a request to join"

    async def execute(self, text, sender):
        if not text:
            raise CommandError(f"usage: {self.usage}")
        key = self.find(text)
        name = self.requests.pop(key)["name"]
        self.store.save()
        # The person isn't told, so a refusal can't start an argument on the air.
        return CommandResult(console=f"Denied {name} ({key[:12]})", reply=f"{self.name}: request from {name} removed")
