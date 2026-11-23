"""Fitting replies into MeshCore's direct messages: 133 characters each, and
at most MAX_PARTS of them for one reply, so a command can't tie up the mesh.
"""

import textwrap

from .errors import CommandError

# Standard MeshCore text message limit for one message.
MAX_REPLY_LEN = 133
# The most messages one reply may take.
MAX_PARTS = 8


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
