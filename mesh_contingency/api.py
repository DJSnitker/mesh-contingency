"""The interface for writing mesh commands, built in or third party.

A command is either a Command subclass or a plain function, registered under
the "mesh_contingency.commands" entry point group (or named directly with
`handler = "module:attr"` in the config). See "Writing a command" in the
README.
"""

import asyncio
import inspect
import textwrap
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .directory import Directory
from .limits import Limits
from .state import State

# Standard MeshCore text message limit for one message.
MAX_REPLY_LEN = 133
# The most messages one reply may take, so a command can't tie up the mesh.
MAX_PARTS = 8
# Seconds a command may run before the bot gives up on it, unless its config
# section sets `timeout`.
DEFAULT_TIMEOUT = 60
# Seconds a destructive command waits to be sent again as confirmation.
CONFIRM_SECONDS = 300

# Who may run a command, set per command in the config's [commands.<name>]
# sections. Only direct messages are handled, so every sender is identified by
# their full public key.
PUBLIC = "public"  # anyone
USER = "user"  # senders with a [users.<key>] section in the users file
ADMIN = "admin"  # senders listed in the users file's [admin] keys
DISABLED = "disabled"  # nobody
LEVELS = (PUBLIC, USER, ADMIN, DISABLED)


@dataclass
class CommandResult:
    console: str  # full output printed locally
    reply: str | list[str] | None  # sent back over the mesh: text, messages in order, or nothing


@dataclass
class Sender:
    name: str  # display name
    # Full 64-hex public key, or None if the sender is not exactly one of the
    # radio's contacts (then only public commands are allowed).
    public_key: str | None


class CommandError(Exception):
    """A failure whose message is safe and short enough to reply with."""


def is_authorized(command, sender, users, admins):
    """Return True if the sender may run the command."""
    if command.permission == PUBLIC:
        return True
    if command.permission == USER:
        return sender.public_key in users
    if command.permission == ADMIN:
        return sender.public_key in admins
    return False


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
    directory: Directory = field(default_factory=Directory)  # the users file, reloaded while running
    radio: object = None  # the connected meshcore.MeshCore
    commands: dict = field(default_factory=dict)  # every loaded command by name, complete once all are built
    state: State = field(default_factory=State)  # senders seen and saved state, shared by all commands
    # send(public key, text): queue a direct message to a contact, sent in the
    # background (so it can't hold up the reply) and logged by the bot.
    send: object = _not_sent
    limits: Limits = field(default_factory=Limits)  # the [limits] settings

    # Read these when they are needed; don't keep a copy. Editing the users
    # file replaces them while the bot runs.
    @property
    def users(self):
        """{public key: that user's [users.<key>] settings}, as of now."""
        return self.directory.users

    @property
    def admins(self):
        """The public keys in [admin] keys, as of now."""
        return self.directory.admins

    def tell_admins(self, text):
        """Send text to every admin, in the background."""
        for key in sorted(self.admins):
            self.send(key, text)

    def name_of(self, sender):
        """The sender's name from the users file, or the name their node advertises."""
        return self.users.get(sender.public_key, {}).get("name") or sender.name

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


def pack(items, limit=MAX_REPLY_LEN, separator="; "):
    """Join items into as few messages of at most `limit` chars as possible,
    without splitting an item (one longer than limit is cut)."""
    messages = []
    for item in items:
        item = item if len(item) <= limit else item[: limit - 3] + "..."
        if messages and len(messages[-1]) + len(separator) + len(item) <= limit:
            messages[-1] += separator + item
        else:
            messages.append(item)
    return messages


def page(messages, number, name, again=None):
    """Return page `number` (from 1) of a long list of mesh messages, each
    page at most MAX_PARTS messages with the last saying how to get the next
    (`again`: what to send, before the page number; the command's name by
    default). Raises CommandError for a page that doesn't exist."""
    per_page = MAX_PARTS - 1  # leaving room to say what's next
    pages = [messages[i:i + per_page] for i in range(0, len(messages), per_page)] or [[]]
    if not 1 <= number <= len(pages):
        raise CommandError(f"{name}: there are {len(pages)} page(s)")
    reply = pages[number - 1]
    if number < len(pages):
        reply = reply + [f"{name}: page {number} of {len(pages)}; send {again or name} {number + 1} for more"]
    return reply


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
    # Set True when what senders write or get back must stay off the console
    # (messages, passphrases): the bot then logs only the command and sender.
    private = False
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
