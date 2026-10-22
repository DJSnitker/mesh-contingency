"""Backups of the bot's data, so a dead disk doesn't lose the users, messages,
check-ins and history: [backup] in config.toml, and the backup command.

Each backup is a new folder named for the time, e.g. 20261022-030000, in the
`to` folder: config.toml, the users file, every JSON file next to
config.toml (check-ins, the mailbox, history...) and the users file's own
backups folder. Files keep their permissions (most are readable only by
their owner), and the folders are made readable only by their owner too.
The newest `keep` are kept; other folders there are never touched.

A backup is made every_hours after the last one (scheduled or not), even
across restarts, so a restart only backs up if one is due. The `to` folder
is best on another disk (a USB stick, a second drive, a network share): a
backup on the same disk is lost with it.
"""

import asyncio
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from .directory import BACKUP_FOLDER

BACKUP_FILE = "backup.json"  # when the last backup was made
BACKUP_KEYS = {"to", "every_hours", "keep"}
DEFAULT_TO = "~/MeshContingencyBackups"
RETRY_SECONDS = 3600  # after a scheduled backup fails
SNAPSHOT_RE = re.compile(r"\d{8}-\d{6}(-\d+)?")  # the folders this makes, and so may remove


class BackupError(Exception):
    """A backup couldn't be made; the message says why, briefly."""


@dataclass(frozen=True)
class BackupSettings:
    to: str = DEFAULT_TO  # as written in config.toml, for messages
    every_hours: float = 24  # 0 for only with the backup command
    keep: int = 7
    folder: Path = Path(DEFAULT_TO).expanduser()  # `to`, as a full path


def load_backup(config, config_dir):
    """BackupSettings from [backup] in config.toml; a relative `to` is
    relative to config_dir. Exits on a mistake."""
    section = config.get("backup", {})
    if not isinstance(section, dict) or set(section) - BACKUP_KEYS:
        raise SystemExit(f"[backup] may only set {', '.join(sorted(BACKUP_KEYS))}.")
    to = section.get("to", DEFAULT_TO)
    if not isinstance(to, str) or not to.strip():
        raise SystemExit('[backup] to must be a folder, e.g. "/mnt/usb/MeshContingencyBackups".')
    every = section.get("every_hours", BackupSettings.every_hours)
    if isinstance(every, bool) or not isinstance(every, (int, float)) or every < 0:
        raise SystemExit("[backup] every_hours must be a number of hours, or 0 for only the backup command.")
    keep = section.get("keep", BackupSettings.keep)
    if isinstance(keep, bool) or not isinstance(keep, int) or keep < 1:
        raise SystemExit("[backup] keep must be a whole number, at least 1.")
    folder = Path(config_dir) / Path(to.strip()).expanduser()
    return BackupSettings(to.strip(), every, keep, folder)


class Backups:
    """Makes backups of the bot's data, on a schedule and when asked."""

    def __init__(self, settings, state, config_path, directory):
        self.settings = settings
        self.state = state
        self.config_path = Path(config_path)
        self.directory = directory
        self.store = state.store(BACKUP_FILE)
        self.failing = None  # why the last backup failed, until one works

    @property
    def last(self):
        """time.time() of the last backup, or None."""
        last = self.store.data.get("last")
        return last if isinstance(last, (int, float)) else None

    def describe(self):
        """For startup."""
        when = f"every {self.settings.every_hours:g} h" if self.settings.every_hours else "only with backup"
        return f"{when} to {self.settings.to} (newest {self.settings.keep} kept)"

    def same_disk(self):
        """True if the backups would be on the same disk as the bot's data."""
        target = self.settings.folder
        while not target.exists() and target != target.parent:
            target = target.parent
        try:
            return target.stat().st_dev == self.config_path.parent.stat().st_dev
        except OSError:
            return False

    def sources(self):
        """[(file, its name in the backup)] for everything to back up."""
        files = [(self.config_path, self.config_path.name)]
        users = self.directory.path
        if users and users.is_file():
            files.append((users, users.name))
        if self.state.data_dir:
            files += [(p, p.name) for p in sorted(self.state.data_dir.glob("*.json")) if p.is_file()]
        if users:
            folder = users.parent / BACKUP_FOLDER
            if folder.is_dir():
                files += [(p, f"{BACKUP_FOLDER}/{p.name}") for p in sorted(folder.iterdir()) if p.is_file()]
        seen, unique = set(), []
        for path, name in files:
            if name not in seen:
                seen.add(name)
                unique.append((path, name))
        return unique

    def snapshots(self):
        """The backup folders there are now, oldest first."""
        root = self.settings.folder
        if not root.is_dir():
            return []
        found = [p for p in root.iterdir() if p.is_dir() and SNAPSHOT_RE.fullmatch(p.name)]
        return sorted(found, key=lambda p: (p.name[:15], self.number(p)))

    @staticmethod
    def number(folder):
        """A backup folder's number within its second: 1, or the -n added."""
        return int(folder.name[16:] or 1)

    def _make(self):
        """Copy everything into a new folder, then remove the oldest beyond
        keep. Returns (the new folder, files copied, folders removed)."""
        root = self.settings.folder
        if not root.exists():
            root.mkdir(parents=True)
            root.chmod(0o700)  # the copies hold keys and messages
        stamp = time.strftime("%Y%m%d-%H%M%S")
        # More than one backup in a second: number it after the newest, even
        # if older ones from that second were removed.
        count = max((self.number(p) for p in self.snapshots() if p.name[:15] == stamp), default=0) + 1
        folder = root / (stamp if count == 1 else f"{stamp}-{count}")
        folder.mkdir(mode=0o700)
        copied = 0
        for path, name in self.sources():
            target = folder / name
            if not target.parent.exists():
                target.parent.mkdir(mode=0o700)
            try:
                shutil.copy2(path, target)  # with its permissions
            except FileNotFoundError:
                continue  # removed meanwhile, e.g. an old users-file backup
            copied += 1
        removed = 0
        for old in self.snapshots()[:-self.settings.keep]:
            shutil.rmtree(old)
            removed += 1
        return folder, copied, removed

    async def make(self, by):
        """Make a backup now; by is who asked ("auto" for the schedule).
        Returns (folder name, files copied, folders removed). Raises
        BackupError, after logging the full reason."""
        try:
            folder, copied, removed = await asyncio.to_thread(self._make)
        except OSError as e:
            print(f"Backup to {self.settings.folder} failed: {e}", flush=True)
            self.failing = e.strerror or type(e).__name__
            self.state.error("backup failed")
            raise BackupError(self.failing) from None
        self.failing = None
        self.store.data["last"] = time.time()
        self.store.save()
        self.state.record(by, f"backed up {copied} file(s) to {folder.name}")
        print(f"Backed up {copied} file(s) to {folder}" + (f"; removed {removed} old backup(s)" if removed else ""),
              flush=True)
        return folder.name, copied, removed

    def seconds_until_due(self):
        """Seconds until the next scheduled backup (0 if one is due)."""
        if self.last is None:
            return 0
        return max(0.0, self.last + self.settings.every_hours * 3600 - time.time())

    async def run(self):
        """Back up whenever one is due, until cancelled; a failed backup is
        tried again in RETRY_SECONDS."""
        while True:
            wait = self.seconds_until_due()
            if wait:
                await asyncio.sleep(wait)
                continue  # check again: the backup command may have made one meanwhile
            try:
                await self.make("auto")
            except BackupError:
                await asyncio.sleep(RETRY_SECONDS)
