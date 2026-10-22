"""What the bot remembers: who has messaged it since it started, and small
JSON files (statuses, the mailbox) kept next to config.toml across restarts.

These files hold node keys and what people wrote, so they are git-ignored and
written readable only by their owner.
"""

import json
import os
import time
from collections import Counter, deque
from pathlib import Path

from .limits import EmailLog

# The audit trail of admin actions (and users leaving), newest last, read
# with the history command.
HISTORY_FILE = "history.json"
MAX_HISTORY = 200


class StoreError(Exception):
    """A state file can't be read; the message says why."""


class Store:
    """A JSON object kept in one file, or only in memory if path is None.

    Change .data, then call save(). The file is replaced in one step, so a
    crash never leaves it half written.
    """

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.data = self._load()

    def _load(self):
        if self.path is None:
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            raise StoreError(f"{self.path} can't be read: {e}") from None
        if not isinstance(data, dict):
            raise StoreError(f"{self.path} doesn't hold a JSON object")
        return data

    def save(self):
        if self.path is None:
            return
        temp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1, ensure_ascii=False)
        os.replace(temp, self.path)


class State:
    """Shared by every command: the senders seen since startup and the state
    files, which live in data_dir (the folder of config.toml), or only in
    memory if data_dir is None."""

    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.started = time.time()
        # key (or the key prefix, for a sender who couldn't be identified) ->
        # (name, time last seen), least recently seen first
        self.seen = {}
        self.emails = EmailLog()  # for the email caps, shared by every email command
        # Since startup, for health: "messages" in, "sent" (replies and notices),
        # "undelivered" (of those) and "errors" (commands that failed or timed out).
        self.counts = Counter()
        self.last_error = None  # (time.time(), e.g. "wx failed")
        self.error_times = deque()  # time.time() of each error in the last day, for the watch
        self.undelivered_in_row = 0  # direct messages not acknowledged since the last one that was
        self.alert_watcher = None  # the AlertWatcher, if [alerts] watches any counties
        self.alert_test = None  # the AlertTest, for testalert and the weekly test
        self.watch = None  # the NodeWatch, if [watch] is enabled
        self._stores = {}

    def saw(self, key, name):
        """Record a direct message from this sender."""
        self.seen.pop(key, None)
        self.seen[key] = (name, time.time())

    def error(self, what):
        """Record a command that failed or timed out, e.g. "wx failed"."""
        self.counts["errors"] += 1
        self.last_error = (time.time(), what)
        self.error_times.append(self.last_error[0])
        while self.error_times[0] < self.last_error[0] - 86400:
            self.error_times.popleft()

    def recent_errors(self, seconds, now=None):
        """How many commands failed or timed out in the last `seconds`."""
        cutoff = (time.time() if now is None else now) - seconds
        return sum(1 for t in self.error_times if t >= cutoff)

    def record(self, by, what):
        """Add an action to the history, e.g. record("Doug", "approved Sam
        (5a3e1c7b9d20)"), keeping the newest MAX_HISTORY."""
        store = self.store(HISTORY_FILE)
        entries = store.data.setdefault("entries", [])
        entries.append({"time": time.time(), "by": by, "what": what})
        del entries[:-MAX_HISTORY]
        store.save()

    def store(self, filename):
        """The Store for a file in data_dir, the same one for every command
        that asks. Raises StoreError if the file is unreadable."""
        if filename not in self._stores:
            self._stores[filename] = Store(self.data_dir / filename if self.data_dir else None)
        return self._stores[filename]


def ago(then, now=None):
    """How long ago a time.time() was, briefly: "just now", "5m ago", "2d ago"."""
    seconds = (time.time() if now is None else now) - then
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit} ago"
    return "just now"
