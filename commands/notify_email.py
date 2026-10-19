"""notify_email <address> <message>: email any address given in the message."""

import re

from .base import CommandError
from .notify_default import NotifyDefaultCommand

# Deliberately strict: the address comes from the mesh and is passed to `mail`
# as an argument, where a leading "-" would be an option and "|" or "/" a pipe
# or file target. Only plain user@domain.tld addresses get through.
ADDRESS_RE = re.compile(r"[A-Za-z0-9._%+][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


class NotifyEmailCommand(NotifyDefaultCommand):
    """Same as notify_default, but the recipient is the first word of the message."""

    name = "notify_email"
    usage = "notify_email <address> <message>"
    # Needs no config: the recipient comes from the message.
    enabled = True

    def __init__(self):
        super().__init__(users={})

    async def execute(self, text, sender):
        parts = text.split(None, 1)
        if len(parts) < 2:
            raise CommandError(f"usage: {self.usage}")
        address, body = parts[0], parts[1].strip()
        if not ADDRESS_RE.fullmatch(address):
            raise CommandError(f"{self.name}: invalid address")
        return await self.send([address], body, sender)
