"""Answering a direct message: find the command it names, check the sender
may run it and isn't over its rate limit, run it and send the reply.

It doesn't depend on the radio: it is given the Sender and a send(key, text)
coroutine function (radio.MeshLink provides both for a MeshCore radio).

What it prints is what happened, never what anyone wrote: the sender's key
prefix and name, the command's name, and how the reply went.
"""

import difflib
import time

from .limits import RateLimiter, describe_rate, wait_text
from .permissions import PUBLIC, is_authorized
from .running import run_command

# Sent for unknown commands and for commands the sender may not run.
UNRECOGNIZED_REPLY = "unrecognized user or function"
# Send UNRECOGNIZED_REPLY to the same sender at most once per this many
# seconds, so another auto-replying node can't trap us in a reply loop.
UNRECOGNIZED_COOLDOWN = 300
# How alike (0-1, difflib's ratio) a mistyped command must be to one the
# sender may run to be suggested: typos like "hlep" or "alret" are 0.75 or
# more; "hello" (help) or "test" (testalert) are less.
SUGGEST_CUTOFF = 0.75


def parse_command(text, commands):
    """Return (command, text after its name) for a message naming one of
    commands ({name: Command}), or None."""
    parts = text.strip().split(None, 1)
    if not parts:
        return None
    command = commands.get(parts[0].lower())
    return (command, parts[1].strip() if len(parts) > 1 else "") if command else None


def nearest_command(word, names, disabled=()):
    """The command in names a mistyped word was meant to be, or None. A
    disabled command's own name gets no suggestion: it's not a typo for
    something else."""
    word = word.lower()
    if word in disabled:
        return None
    close = difflib.get_close_matches(word, names, n=1, cutoff=SUGGEST_CUTOFF)
    return close[0] if close else None


class Dispatcher:
    """Hands each direct message to its command.

    commands is {name: Command}, as Registry.build returns; roles says who
    are users and admins; send(key, text) is a coroutine function sending one
    direct message, to a full public key or the key prefix a message came
    with. disabled names commands nobody may run, so they aren't suggested as
    typos of others.
    """

    def __init__(self, commands, roles, send, disabled=()):
        self.commands = commands
        self.roles = roles
        self.send = send
        self.disabled = disabled
        self.limiter = RateLimiter()  # uses of each command by each sender
        self._last_unrecognized = {}  # key prefix -> time.monotonic() of the last UNRECOGNIZED_REPLY

    def allowed(self, command, sender):
        return is_authorized(command, sender, self.roles)

    async def handle(self, prefix, sender, text):
        """Answer one direct message: text, from the Sender, which came with
        the key prefix `prefix` (12 hex characters)."""
        label = prefix if sender.name == prefix else f"{prefix} {sender.name}"
        parsed = parse_command(text, self.commands)
        # Only the command's name is printed, never what was sent with it or
        # what doesn't parse as a command.
        print(f"[{label}] {parsed[0].name if parsed else 'not a command'}", flush=True)

        async def reply(message):
            await self.send(sender.public_key or prefix, message)

        if parsed is None:
            words = text.split()
            if not words:
                return
            # A sender with rights beyond the public commands is told the
            # nearest command they may run; others learn nothing about the
            # commands there are.
            mine = [c.name for c in self.commands.values() if self.allowed(c, sender)]
            if any(self.commands[name].permission != PUBLIC for name in mine):
                nearest = nearest_command(words[0], mine, self.disabled)
                if nearest:
                    print(f"  -> unrecognized command; suggesting {nearest}", flush=True)
                    await reply(f"unknown command {words[0][:30]}; did you mean {nearest}? help lists yours")
                    return
            await self._unrecognized(prefix, reply, "unrecognized command")
            return
        command, text = parsed
        if not self.allowed(command, sender):
            await self._unrecognized(prefix, reply, f"{command.name} denied: sender not approved")
            return
        wait, first = self.limiter.check(sender.public_key or prefix, command.name, command.rate)
        if wait:
            # Told once; after that silence, so the limit can't make us transmit.
            if first:
                print(f"  -> {command.name} limit reached ({describe_rate(command.rate)}); replying once", flush=True)
                await reply(f"{command.name}: limit reached, try again in {wait_text(wait)}")
            else:
                print(f"  -> {command.name} limit reached; not replying", flush=True)
            return
        answer = await run_command(command, text, sender)
        # A long reply comes as several messages, sent in order.
        for message in answer.messages:
            await reply(message)
            print(f"  -> replied ({len(message)} chars)", flush=True)

    async def _unrecognized(self, prefix, reply, why):
        """Send UNRECOGNIZED_REPLY unless this sender got one recently."""
        now = time.monotonic()
        if now - self._last_unrecognized.get(prefix, -UNRECOGNIZED_COOLDOWN) < UNRECOGNIZED_COOLDOWN:
            print(f"  -> {why}; not replying (replied within {UNRECOGNIZED_COOLDOWN}s)", flush=True)
            return
        self._last_unrecognized[prefix] = now
        print(f"  -> {why}; sending unrecognized reply", flush=True)
        await reply(UNRECOGNIZED_REPLY)
