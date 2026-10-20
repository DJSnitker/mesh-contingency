"""Base class shared by all mesh commands."""

import textwrap
from abc import ABC, abstractmethod
from dataclasses import dataclass

# Standard MeshCore text message limit for a reply.
MAX_REPLY_LEN = 133

# Who may run a command. Only direct messages are handled, so every sender is
# identified by their pubkey prefix.
PUBLIC = "public"  # anyone
USER = "user"  # senders with a [users.<key>] config section
ADMIN = "admin"  # senders listed in [admin] keys


@dataclass
class CommandResult:
    console: str  # full output printed locally
    reply: str | list[str]  # text sent back over the mesh: one message, or several in order


@dataclass
class Sender:
    name: str  # display name
    key: str  # 12-hex-char pubkey prefix


class CommandError(Exception):
    """A failure whose message is safe and short enough to reply with."""


class Command(ABC):
    """One mesh command, triggered by a message of the form "<name> <text>"."""

    name: str
    usage: str
    # Set False (e.g. as a property) when required config is missing.
    enabled = True
    # PUBLIC, USER or ADMIN; see above.
    permission = PUBLIC

    @abstractmethod
    async def execute(self, text, sender):
        """Run the command and return a CommandResult.

        text is everything after the command name, as sent (whitespace
        trimmed); sender is the Sender of the message.
        """

    @staticmethod
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

    @staticmethod
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
