"""Writing a command: a Command subclass, or a plain function.

A command answers direct messages of the form "<name> <text>". It is named
in the config's [commands] table and found through an entry point group the
project picks, or named directly with handler = "module:attr" (see
registry.py).
"""

import asyncio
import inspect
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .permissions import DISABLED, NO_ROLES, is_authorized
from .replies import fit_reply, split_reply

# Seconds a command may run before it is given up on, unless its config
# section sets `timeout`.
DEFAULT_TIMEOUT = 60
# Seconds a destructive command waits to be sent again as confirmation.
CONFIRM_SECONDS = 300


@dataclass
class CommandResult:
    console: str  # full output, for the project to print or keep (the dispatcher prints none of it)
    reply: str | list[str] | None  # sent back over the mesh: text, messages in order, or nothing


@dataclass
class Sender:
    name: str  # display name
    # Full 64-hex public key, or None if the sender is not exactly one of the
    # radio's contacts (then only public commands are allowed).
    public_key: str | None


class Confirmations:
    """Asking before something that can't be undone: the first time someone
    sends a command it only says what would happen, and it acts if they send
    the same thing again within CONFIRM_SECONDS."""

    def __init__(self):
        self._waiting = {}  # who -> (what, time.monotonic())

    def confirmed(self, who, what):
        """Return True if `who` asked for `what` (any comparable value)
        within CONFIRM_SECONDS; otherwise remember this request and return
        False. Asking for anything else starts over."""
        now = time.monotonic()
        previous = self._waiting.pop(who, None)
        if previous is not None and previous[0] == what and now - previous[1] < CONFIRM_SECONDS:
            return True
        self._waiting[who] = (what, now)
        return False


def _not_sent(public_key, text):
    """Context.send when there is no radio to send with."""


@dataclass
class Context:
    """What a command is given when it is created."""

    name: str  # the name the command answers to
    options: dict = field(default_factory=dict)  # its [commands.<name>] settings, e.g. {"station": "..."}
    radio: object = None  # the connected meshcore.MeshCore
    commands: dict = field(default_factory=dict)  # every loaded command by name, complete once all are built
    # send(public key, text): queue a direct message to a contact, sent in the
    # background (so it can't hold up the reply).
    send: object = _not_sent
    roles: object = NO_ROLES  # who are users and admins (see permissions.Roles)
    extras: dict = field(default_factory=dict)  # whatever the project passes to its commands

    def allowed(self, command, sender):
        """Return True if the sender may run the command."""
        return is_authorized(command, sender, self.roles)


class Command(ABC):
    """One mesh command, triggered by a message of the form "<name> <text>".

    Subclasses are created with the Context for their name, and set:
      args     argument synopsis for usage and help, e.g. "<zipcode>"
      summary  one line saying what it does, for help
    """

    args = ""
    summary = ""
    # Set False (e.g. as a property) when required config is missing.
    enabled = True
    # Uses allowed per sender, as (count, seconds), or None for no limit; set
    # from the config when the command is loaded.
    rate = None
    # One of LEVELS, and the time limit; both set from the config when the
    # command is loaded.
    permission = DISABLED
    timeout = DEFAULT_TIMEOUT

    def __init__(self, ctx):
        self.ctx = ctx
        self.name = ctx.name

    @property
    def usage(self):
        return f"{self.name} {self.args}".strip()

    async def start(self):
        """Called once at startup, after the radio connects and before any
        message is handled, for setup that needs the radio. Return a line to
        print, or None. If it raises, a warning is printed and the command
        still runs."""
        return None

    @abstractmethod
    async def execute(self, text, sender):
        """Run the command and return a CommandResult, or just the reply text.

        text is everything after the command name, as sent (whitespace
        trimmed); sender is the Sender of the message. Raise CommandError for
        a failure whose message should be sent back; any other exception is
        logged and answered with "<name>: failed".
        """

    fit_reply = staticmethod(fit_reply)
    split_reply = staticmethod(split_reply)


def command(args="", summary=""):
    """Decorate a function command with its argument synopsis and summary.

        @command(args="<sides>", summary="Roll a die")
        def roll(text, sender, ctx): ...

    Without it, a function command has no args and its summary is the first
    line of its docstring.
    """
    def decorate(func):
        func.args = args
        func.summary = summary
        return func
    return decorate


class FunctionCommand(Command):
    """Wraps a plain function `func(text, sender, ctx)`, sync or async, as a
    Command. It returns what execute() would: reply text, a list of messages,
    a CommandResult or None."""

    def __init__(self, ctx, func):
        super().__init__(ctx)
        self.func = func
        self.args = getattr(func, "args", "")
        doc = (inspect.getdoc(func) or "").strip().splitlines()
        self.summary = getattr(func, "summary", "") or (doc[0] if doc else "")

    async def execute(self, text, sender):
        if inspect.iscoroutinefunction(self.func):
            return await self.func(text, sender, self.ctx)
        # Run blocking functions off the event loop so the radio keeps working.
        return await asyncio.to_thread(self.func, text, sender, self.ctx)
