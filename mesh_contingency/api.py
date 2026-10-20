"""The interface for writing mesh commands, built in or third party.

A command is either a Command subclass or a plain function, registered under
the "mesh_contingency.commands" entry point group (or named directly with
`handler = "module:attr"` in the config). See "Writing a command" in the
README.
"""

import asyncio
import inspect
import textwrap
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# Standard MeshCore text message limit for one message.
MAX_REPLY_LEN = 133
# The most messages one reply may take, so a command can't tie up the mesh.
MAX_PARTS = 8
# Seconds a command may run before the bot gives up on it, unless its config
# section sets `timeout`.
DEFAULT_TIMEOUT = 60

# Who may run a command, set per command in the config's [commands.<name>]
# sections. Only direct messages are handled, so every sender is identified by
# their pubkey prefix.
PUBLIC = "public"  # anyone
USER = "user"  # senders with a [users.<key>] config section
ADMIN = "admin"  # senders listed in [admin] keys
DISABLED = "disabled"  # nobody
LEVELS = (PUBLIC, USER, ADMIN, DISABLED)


@dataclass
class CommandResult:
    console: str  # full output printed locally
    reply: str | list[str] | None  # sent back over the mesh: text, messages in order, or nothing


@dataclass
class Sender:
    name: str  # display name
    key: str  # 12-hex-char pubkey prefix


class CommandError(Exception):
    """A failure whose message is safe and short enough to reply with."""


def is_authorized(command, sender, users, admins):
    """Return True if the sender may run the command."""
    if command.permission == PUBLIC:
        return True
    if command.permission == USER:
        return sender.key in users
    if command.permission == ADMIN:
        return sender.key in admins
    return False


@dataclass
class Context:
    """What a command is given when it is created."""

    name: str  # the name the command answers to
    options: dict = field(default_factory=dict)  # its [commands.<name>] settings, e.g. {"station": "..."}
    users: dict = field(default_factory=dict)  # pubkey prefix -> that user's [users.<key>] settings
    admins: set = field(default_factory=set)  # pubkey prefixes in [admin] keys
    radio: object = None  # the connected meshcore.MeshCore
    commands: dict = field(default_factory=dict)  # every loaded command by name, complete once all are built

    def allowed(self, command, sender):
        """Return True if the sender may run the command."""
        return is_authorized(command, sender, self.users, self.admins)


def fit_reply(prefix, sections, limit=MAX_REPLY_LEN):
    """Join prefix and sections into one line of at most `limit` chars.

    Sections are in priority order; a section that no longer fits is
    dropped rather than cut off, except the first, which is truncated so
    the most important information is never lost.
    """
    text = prefix
    for i, section in enumerate(sections):
        candidate = f"{text} {section}" if i == 0 else f"{text} | {section}"
        if len(candidate) <= limit:
            text = candidate
        elif i == 0:
            text = candidate[: limit - 3] + "..."
            break
    return text


def split_reply(text, limit=MAX_REPLY_LEN):
    """Split text into messages of at most `limit` chars, breaking between words.

    Text that fits is returned as a single message. Otherwise every message
    is numbered "(i/n) " so the receiver can put them back in order even if
    the mesh delivers them out of sequence.
    """
    if len(text) <= limit:
        return [text]
    count = 2
    while True:
        width = limit - len(f"({count}/{count}) ")
        chunks = textwrap.wrap(text, width, break_on_hyphens=False)
        # Only accept once the numbering is at least as wide as assumed.
        if len(chunks) <= count:
            return [f"({i}/{len(chunks)}) {chunk}" for i, chunk in enumerate(chunks, 1)]
        count = len(chunks)


def to_messages(reply):
    """Return the mesh messages for a command's reply, within the mesh limits.

    Text is split into numbered messages, shortened if it would need more
    than MAX_PARTS. A list is sent as given, with each message cut to
    MAX_REPLY_LEN and the list to MAX_PARTS. None means no reply.
    """
    if reply is None:
        return []
    if isinstance(reply, str):
        messages = split_reply(reply)
        while len(messages) > MAX_PARTS:
            reply = reply[: len(reply) * 9 // 10].rsplit(" ", 1)[0] + "..."
            messages = split_reply(reply)
        return messages
    return [m if len(m) <= MAX_REPLY_LEN else m[: MAX_REPLY_LEN - 3] + "..." for m in reply[:MAX_PARTS]]


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
