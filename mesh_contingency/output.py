"""Keeping what the bot prints safe for a terminal.

Message text, node names and error text all come from the mesh, and anyone
can put terminal control sequences in them: ESC sequences that recolour or
clear the screen, set the window title, or rewrite earlier lines with a
carriage return, and Unicode controls that reverse how text displays. The bot
prints through SafeOutput, which shows them as visible escapes instead, e.g.
"\\x1b[2J". Newlines and tabs, accents and emoji are left alone.
"""

import re

# C0 and C1 controls other than tab and newline, DEL, and the Unicode
# bidirectional controls (embeddings, overrides, isolates, marks).
UNSAFE_RE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f؜‎‏‪-‮⁦-⁩]")


def _escape(match):
    code = ord(match.group())
    return f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}"


def printable(text):
    """text with every control character shown as a visible escape."""
    return UNSAFE_RE.sub(_escape, text)


class SafeOutput:
    """A stand-in for sys.stdout that escapes control characters in all it's
    given before passing it on."""

    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        return self.stream.write(printable(text))

    def __getattr__(self, name):  # flush, isatty, fileno, encoding...
        return getattr(self.stream, name)
