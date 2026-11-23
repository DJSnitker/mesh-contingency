"""What the bot keeps across restarts: small JSON files next to config.toml
(the alerts already posted, when the last advert and test went out).

They're git-ignored and written readable only by their owner.
"""

import json
import os
import time
from pathlib import Path


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
    """Shared by every command: the state files, which live in data_dir (the
    folder of config.toml), or only in memory if data_dir is None."""

    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.started = time.time()
        self.alert_watcher = None  # the AlertWatcher, if [alerts] watches any counties
        self.alert_test = None  # the AlertTest, for testalert and the weekly test
        self.channel = None  # [alerts] channel, for alert (None: Public)
        self._stores = {}

    def store(self, filename):
        """The Store for a file in data_dir, the same one for every command
        that asks. Raises StoreError if the file is unreadable."""
        if filename not in self._stores:
            self._stores[filename] = Store(self.data_dir / filename if self.data_dir else None)
        return self._stores[filename]


def duration(seconds):
    """A length of time in its two largest units: "2d 3h", "3h 5m", "12m"."""
    seconds = int(seconds)
    days, hours, minutes = seconds // 86400, seconds % 86400 // 3600, seconds % 3600 // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

