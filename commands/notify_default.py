"""notify_default <message>: email a preconfigured user."""

import asyncio
import subprocess

from .base import USER, Command, CommandError, CommandResult, Sender

SUBJECT = "You have received a MeshCore message from: {sender}"
DISCLAIMER = (
    "This message was triggered from an external relayed radio signal, as a one way "
    "communication.  Replies to this mailbox are unmonitored and will not carry a "
    "message back to the sender, please contact them directly"
)
# Every notification email: the mesh text, a blank line, then the disclaimer.
BODY = "{text}\n\n{disclaimer}"
TIMEOUT = 30


def send_email(to, subject, body):
    """Send an email to a list of addresses with the `mail` command line tool.

    Everything is passed as argv or stdin and never through a shell. Callers
    must validate any address that comes from the mesh (see notify_email).
    """
    # The subject holds the mesh sender's name; drop control characters so a
    # crafted name cannot add lines or headers.
    subject = "".join(ch for ch in subject if ch.isprintable())
    # mail treats a line starting with "~" as a command escape in some modes;
    # indent such lines so mesh text can never be interpreted.
    body = "\n".join(" " + line if line.startswith("~") else line for line in body.splitlines())
    try:
        result = subprocess.run(
            ["mail", "-s", subject, *to],
            input=body + "\n",
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except FileNotFoundError as e:
        raise RuntimeError("`mail` command not found") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"`mail` timed out after {TIMEOUT}s") from e
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit status {result.returncode}"
        raise RuntimeError(f"`mail` failed: {detail}")


class NotifyDefaultCommand(Command):
    name = "notify_default"
    usage = "notify_default <message>"
    permission = USER

    def __init__(self, users):
        # Each user's addresses for this command live under the command's own
        # name in their [users.<key>] config section: one address or a list.
        self.recipients = {}
        for key, user in users.items():
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
        return await self.send(to, text, sender)

    async def send(self, to, text, sender: Sender):
        """Email text to the given addresses and return the CommandResult."""
        subject = SUBJECT.format(sender=sender.name)
        body = BODY.format(text=text, disclaimer=DISCLAIMER)
        await asyncio.to_thread(send_email, to, subject, body)
        return CommandResult(
            console=f"Sent email to {', '.join(to)}\n  Subject: {subject}\n  Body: {text}",
            reply=f"{self.name}: sent",
        )
