"""email <address> <message>: email any address given in the message."""

from ..api import CommandError
from .mail import ADDRESS_RE, MailCommand


class EmailCommand(MailCommand):
    args = "<address> <message>"
    summary = "Email your message to any address"

    async def execute(self, text, sender):
        parts = text.split(None, 1)
        if len(parts) < 2:
            raise CommandError(f"usage: {self.usage}")
        address, body = parts[0], parts[1].strip()
        if not ADDRESS_RE.fullmatch(address):
            raise CommandError(f"{self.name}: invalid address")
        return await self.send([address], body, sender)
