"""quickim <message>: email the sender's preconfigured contact."""

from ..api import CommandError, Sender
from .email import EmailCommand
from .mail import ADDRESS_RE, MailCommand


class QuickImCommand(MailCommand):
    args = "<message>"
    summary = "Email your message to your preset contact"

    def __init__(self, ctx):
        super().__init__(ctx)
        # Each user's addresses for this command live under the command's own
        # name in their [users.<key>] config section: one address or a list.
        self.recipients = {}
        for key, user in ctx.users.items():
            to = user.get(self.name)
            to = [to] if isinstance(to, str) else list(to or [])
            if to:
                self.recipients[key] = to

    @property
    def enabled(self):
        return bool(self.recipients)

    async def execute(self, text, sender: Sender):
        if not text:
            raise CommandError(f"usage: {self.usage}")
        to = self.recipients.get(sender.key)
        if not to:
            raise CommandError(f"{self.name}: not configured for you")
        if ADDRESS_RE.fullmatch(text.split()[0]):
            # Most likely meant for the email command; don't send it to the
            # preset contact by mistake.
            raise CommandError(f"{self.name}: message starts with an address; {self._email_hint(sender)}")
        return await self.send(to, text, sender)

    def _email_hint(self, sender):
        """Point the sender at an email command they may run, if there is one."""
        for cmd in self.ctx.commands.values():
            if isinstance(cmd, EmailCommand) and self.ctx.allowed(cmd, sender):
                return f"to email it, use {cmd.usage}"
        return "send just the message"
