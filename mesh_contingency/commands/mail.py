"""Sending mesh messages out as email, shared by the qm, emailall and
email commands.

An email that can't be sent is not kept to try again: the sender is told why,
in a few safe words, and the full reason goes to the console.
"""

import asyncio
import os
import re
import subprocess
import time

from ..api import Command, CommandError, CommandResult, Sender

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
ADDRESS_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")

# Why an email wasn't sent, as (cause, what to do) for the sender's reply.
# Never mail's own output, which can hold the node's email address.
NO_INTERNET = ("no internet at the node", "try again later")
LOGIN_REFUSED = ("the node's email login was refused", "tell an admin")
ADDRESS_REFUSED = ("an address was refused", "check the address")
TIMED_OUT = ("email timed out", "try again later")
NOT_SET_UP = ("email isn't set up on the node", "tell an admin")
OTHER = ("email error at the node", "tell an admin")
# Phrases in the error output of mail (and msmtp, which it sends through),
# checked in order, lower case.
CAUSES = [
    (("authentication failed", "username and password not accepted"), LOGIN_REFUSED),
    (("recipient address",), ADDRESS_REFUSED),
    (("cannot locate host", "cannot connect", "name resolution", "network", "timed out"), NO_INTERNET),
]


class SendError(RuntimeError):
    """An email that wasn't sent: the message is the full reason, for the
    console; .reason is (cause, what to do), safe to tell the sender."""

    def __init__(self, detail, reason):
        super().__init__(detail)
        self.reason = reason


def reason_for(output):
    """The (cause, what to do) that mail's error output points to."""
    output = output.lower()
    for phrases, reason in CAUSES:
        if any(phrase in output for phrase in phrases):
            return reason
    return OTHER


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
            # s-nail saves a message it couldn't send to ~/dead.letter, where
            # it would sit unsealed; DEAD sends it nowhere instead.
            env={**os.environ, "DEAD": "/dev/null"},
        )
    except FileNotFoundError as e:
        raise SendError("`mail` command not found", NOT_SET_UP) from e
    except subprocess.TimeoutExpired as e:
        raise SendError(f"`mail` timed out after {TIMEOUT}s", TIMED_OUT) from e
    if result.returncode != 0:
        output = (result.stderr or result.stdout).strip()
        detail = " ".join(output.split()) or f"exit status {result.returncode}"
        raise SendError(f"`mail` failed: {detail}", reason_for(output))


class MailCommand(Command):
    """Base for commands that email the sender's message."""

    private = True  # the message, and who it's to

    def check_caps(self, to, sender):
        """Raise CommandError if emailing `to` would pass a daily email cap
        ([limits] emails_per_day: emails the sender sent, one per command;
        emails_per_day_total: addresses everyone emailed, since the sending
        account's own limits count recipients)."""
        log, limits = self.ctx.state.emails, self.ctx.limits
        if limits.emails_per_day and log.sends(sender.public_key) >= limits.emails_per_day:
            raise CommandError(f"{self.name}: you've reached your daily email limit "
                               f"({limits.emails_per_day}); try again later")
        if limits.emails_per_day_total and log.addresses() + len(to) > limits.emails_per_day_total:
            raise CommandError(f"{self.name}: the node's daily email limit is reached; try again later")

    async def send(self, to, text, sender: Sender):
        """Email text to the given addresses and return the CommandResult."""
        self.check_caps(to, sender)
        subject = SUBJECT.format(sender=sender.name)
        body = BODY.format(text=text, disclaimer=DISCLAIMER)
        try:
            await asyncio.to_thread(send_email, to, subject, body)
        except SendError as e:
            cause, todo = e.reason
            emails = self.ctx.state.emails
            emails.last_failure = (time.time(), cause)
            if e.reason != ADDRESS_REFUSED:
                emails.failing = cause
            # The bot replies with this instead of "<command>: failed".
            e.reply = f"{self.name}: not sent, {cause}; {todo}"
            raise
        self.ctx.state.emails.record(sender.public_key, len(to))
        self.ctx.state.emails.failing = None
        return CommandResult(
            console=f"Sent email to {len(to)} address(es)",
            reply=f"{self.name}: sent",
        )
