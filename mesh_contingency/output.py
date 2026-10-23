"""Keeping what the bot prints safe for a terminal.

Message text, node names and error text all come from the mesh, and anyone
can put terminal control sequences in them: ESC sequences that recolour or
clear the screen, set the window title, or rewrite earlier lines with a
carriage return, and Unicode controls that reverse how text displays. The bot
prints through SafeOutput, which shows them as visible escapes instead, e.g.
"\\x1b[2J". Newlines and tabs, accents and emoji are left alone.

SafeOutput can also keep the last lines printed and hand each new one to
listeners, for the web console's live log. What it gets is what the
terminal and the journal get, so a private command's text, which the bot
never prints, never reaches it either.
"""

import re
import threading
import time
from collections import deque

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
    given before passing it on, keeping the last `keep` lines."""

    def __init__(self, stream, keep=0):
        self.stream = stream
        self.lines = deque(maxlen=keep)  # (time.time(), line), oldest first
        self._listeners = set()  # listener(time, line) for each new line
        self._partial = ""  # printed since the last newline
        # Printing from another thread (asyncio.to_thread) mustn't lose lines.
        self._lock = threading.Lock()

    def write(self, text):
        text = printable(text)
        if self.lines.maxlen:
            self._keep(text)
        return self.stream.write(text)

    def _keep(self, text):
        with self._lock:
            *done, self._partial = (self._partial + text).split("\n")
            now = time.time()
            for line in done:
                self.lines.append((now, line))
            listeners = list(self._listeners)
        for line in done:
            for listener in listeners:
                listener(now, line)

    def listen(self, listener):
        """Call listener(time, line) for each line printed from now on, and
        return the lines kept so far, with none missed or repeated between."""
        with self._lock:
            self._listeners.add(listener)
            return list(self.lines)

    def unlisten(self, listener):
        with self._lock:
            self._listeners.discard(listener)

    def __getattr__(self, name):  # flush, isatty, fileno, encoding...
        return getattr(self.stream, name)
