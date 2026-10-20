"""Sending mesh messages out as email, shared by the quickim, emailall and
email commands."""

import asyncio
import re
import subprocess

from ..api import Command, CommandResult, Sender

SUBJECT = "You have received a MeshCore message from: {sender}"
DISCLAIMER = (
    "This message was triggered from an external relayed radio signal, as a one way "
    "communication.  Replies to this mailbox are unmonitored and will not carry a "
    "message back to the sender, please contact them directly"
)
# Every notification email: the mesh text, a blank line, then the disclaimer.
BODY = "{text}\n\n{disclaimer}"
TIMEOUT = 30
# Deliberately strict: the address comes from the mesh and is passed to `mail`
# as an argument, where a leading "-" would be an option and "|" or "/" a pipe
# or file target. Only plain user@domain.tld addresses get through.
ADDRESS_RE = re.compile(r"[A-Za-z0-9._%+][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def send_email(to, subject, body):
    """Send an email to a list of addresses with the `mail` command line tool.

    Everything is passed as argv or stdin and never through a shell. Callers
    must validate any address that comes from the mesh with ADDRESS_RE.
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


class MailCommand(Command):
    """Base for commands that email the sender's message."""

    async def send(self, to, text, sender: Sender):
        """Email text to the given addresses and return the CommandResult."""
        subject = SUBJECT.format(sender=sender.name)
        body = BODY.format(text=text, disclaimer=DISCLAIMER)
        await asyncio.to_thread(send_email, to, subject, body)
        return CommandResult(
            console=f"Sent email to {', '.join(to)}\n  Subject: {subject}\n  Body: {text}",
            reply=f"{self.name}: sent",
        )
