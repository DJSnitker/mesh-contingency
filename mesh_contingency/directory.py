"""The users file: who may run user and admin commands, reloaded while the bot runs.

    # users.toml
    [admin]
    keys = ["<64-hex public key>"]

    [users.<64-hex public key>]
    name = "Alice T-Deck"             # the radio's name; kept up to date by the bot
    quickim = "someone@example.com"   # settings for the commands

The bot checks the file every few seconds. A change is used only once the file
has stopped changing and has been read and checked in full, so a half-saved
file or a bad edit never locks anyone out: the previous users stay in effect
until the file is fixed.

Commands can also write one user's section (approve, setquickim, ...). Only
that section is rewritten; the rest of the file, comments included, is kept.

A user's name is always their radio's name: the bot writes it when they join
and updates it when it sees the radio go by another name. Commands that name
a user accept it as typed ("msg Ridge Base 1 hi") or in « » ("msg «Ridge Base 1»
hi"), which marks where a name with spaces or punctuation ends.
"""

import asyncio
import json
import os
import re
import time
import tomllib
from pathlib import Path

DEFAULT_FILE = "users.toml"
# Before the bot rewrites the users file, the old version is saved in this
# folder next to it; the newest BACKUPS are kept.
BACKUP_FOLDER = "backups"
BACKUPS = 5
DEFAULT_RELOAD_SECONDS = 5
DIRECTORY_KEYS = {"file", "reload_seconds"}
PUBLIC_KEY_RE = re.compile(r"[0-9a-f]{64}")
# A key prefix naming a user: at least 4 hex characters.
KEY_PREFIX_RE = re.compile(r"[0-9a-f]{4,64}")
_NOTHING = object()  # no change waiting (a missing file's signature is None)


class DirectoryError(Exception):
    """The users file can't be used; the message says why."""


def _show(value):
    """A config value for an error message, shortened so a long key is never
    copied out in full."""
    text = repr(value)
    return text if len(text) <= 20 else text[:16] + "...'"


def public_key(key, where):
    """Return a full public key from the users file in lowercase; raise
    DirectoryError if it is anything else, such as just the prefix."""
    normalized = key.strip().lower() if isinstance(key, str) else key
    if not isinstance(normalized, str) or not PUBLIC_KEY_RE.fullmatch(normalized):
        raise DirectoryError(f"{where}: {_show(key)} is not a full public key (64 hex characters)")
    return normalized


def parse(data):
    """Return (users, admins) from a parsed users file: {public key: settings}
    and a frozenset of public keys. Raises DirectoryError on any mistake."""
    unknown = sorted(set(data) - {"admin", "users"})
    if unknown:
        raise DirectoryError(f"unknown section(s) {', '.join(unknown)}; use [admin] and [users.<key>]")
    admin = data.get("admin", {})
    if not isinstance(admin, dict) or set(admin) - {"keys"}:
        raise DirectoryError('[admin] must only hold keys = ["<public key>", ...]')
    keys = admin.get("keys", [])
    if not isinstance(keys, list):
        raise DirectoryError("[admin] keys must be a list")
    admins = frozenset(public_key(key, "[admin] keys") for key in keys)

    users = {}
    for key, settings in data.get("users", {}).items():
        normalized = public_key(key, "[users]")
        if not isinstance(settings, dict):
            raise DirectoryError(f"[users.{_show(key)[1:-1]}] must be a table")
        if normalized in users:
            raise DirectoryError(f"[users]: {_show(key)} is listed twice")
        if not isinstance(settings.get("name", ""), str):
            raise DirectoryError(f"[users.{_show(key)[1:-1]}] name must be text")
        users[normalized] = settings
    return users, admins


def describe(key, users):
    """A user's name from the file, or their key prefix."""
    return users.get(key, {}).get("name") or key[:12]


def possessive(name):
    """ "Alice's", but "fourbirds'" for a name ending in s."""
    return f"{name}'" if name.lower().endswith("s") else f"{name}'s"


def unquote(text):
    """(name, rest) for text starting with a name in « », e.g. "«Ridge Base 1» hi";
    None if it doesn't start with «."""
    text = text.lstrip()
    if not text.startswith("«") or "»" not in text:
        return None
    name, _, rest = text[1:].partition("»")
    return name.strip(), rest.strip()


class AmbiguousUser(LookupError):
    """Several users have the name; the message lists their key prefixes."""


def find_user(users, text):
    """Return (public key, rest of text) for text starting with a user's name
    or key prefix, or None. A name may be in « ». Otherwise the longest name
    wins, so "Ann Lee hi" isn't for "Ann"; a key prefix must match exactly one
    user. Raises AmbiguousUser if several users have the name."""
    def only(keys, name):
        if len(keys) > 1:
            raise AmbiguousUser(f"{len(keys)} users are called {name}; use the key prefix: "
                                + ", ".join(sorted(k[:12] for k in keys)))
        return keys[0]

    named = [(key, user["name"]) for key, user in users.items() if user.get("name")]
    quoted = unquote(text)
    if quoted:
        name, rest = quoted
        keys = [key for key, n in named if n.lower() == name.lower()]
        return (only(keys, name), rest) if keys else None
    lowered = text.lower()
    for _, name in sorted(named, key=lambda kn: -len(kn[1])):
        rest = text[len(name):]
        if lowered.startswith(name.lower()) and (not rest or rest[0].isspace()):
            keys = [k for k, n in named if n.lower() == name.lower()]
            return only(keys, name), rest.strip()
    first, _, rest = text.partition(" ")
    if KEY_PREFIX_RE.fullmatch(first.lower()):
        keys = [key for key in users if key.startswith(first.lower())]
        if len(keys) == 1:
            return keys[0], rest.strip()
    return None


def summarize(old_users, old_admins, new_users, new_admins):
    """Describe what a reload changed, e.g. "added Bob; removed Carol"."""
    def names(keys, users):
        return ", ".join(sorted(describe(k, users) for k in keys))

    both = {**old_users, **new_users}
    parts = []
    for label, keys, users in [
        ("added", new_users.keys() - old_users.keys(), new_users),
        ("removed", old_users.keys() - new_users.keys(), old_users),
        ("changed", {k for k in new_users.keys() & old_users.keys() if new_users[k] != old_users[k]}, new_users),
        ("admin added", new_admins - old_admins, both),
        ("admin removed", old_admins - new_admins, both),
    ]:
        if keys:
            parts.append(f"{label} {names(keys, users)}")
    return "; ".join(parts) or "no changes"


TABLE_RE = re.compile(r"\s*\[")  # a line starting a [table]
BARE_KEY_RE = re.compile(r"[A-Za-z0-9_-]+")


def toml_value(value):
    """A value written as TOML: text, true/false, a number, a list or an
    inline table. Raises ValueError for anything else."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        # A JSON string is a TOML basic string, apart from DEL, which TOML
        # wants escaped.
        return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{toml_key(k)} = {toml_value(v)}" for k, v in value.items()) + "}"
    raise ValueError(f"can't write {type(value).__name__} values")


def toml_key(key):
    return key if BARE_KEY_RE.fullmatch(key) else toml_value(key)


def with_user(text, key, settings):
    """Return the users file text with [users.<key>] replaced by settings, or
    added at the end if it isn't there; settings None removes the section.
    Comments and blank lines after the section's last setting stay, since
    they usually describe what follows."""
    section = [] if settings is None else (
        [f"[users.{key}]\n"] + [f"{toml_key(k)} = {toml_value(v)}\n" for k, v in settings.items()])
    header = re.compile(rf"\s*\[\s*users\s*\.\s*\"?{key}\"?\s*\]\s*(#.*)?", re.IGNORECASE)
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if header.fullmatch(line.rstrip("\r\n"))), None)
    if start is None:
        if settings is None:
            return text
        text = text.rstrip("\n")
        return (text + "\n\n" if text else "") + "".join(section)
    end = next((i for i in range(start + 1, len(lines)) if TABLE_RE.match(lines[i])), len(lines))
    while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    return "".join(lines[:start] + section + lines[end:])


class Directory:
    """The current users and admins.

    Read .users and .admins at the moment of use rather than keeping a copy:
    a reload replaces them.
    """

    def __init__(self, users=None, admins=None, path=None, reload_seconds=DEFAULT_RELOAD_SECONDS):
        self.path = Path(path) if path is not None else None
        self.reload_seconds = reload_seconds
        self._users = dict(users or {})
        self._admins = frozenset(admins or ())
        self.on_change = []  # functions called with the summary after each reload
        self._seen = None  # signature of the file version last acted on
        self._pending = _NOTHING  # a changed signature waiting to be seen again
        self.loaded = None  # time.time() of the last successful (re)load
        self.problem = None  # (time.time(), reason) if the last reload failed

    @property
    def users(self):
        """{public key: that user's settings}"""
        return self._users

    @property
    def admins(self):
        """frozenset of admin public keys"""
        return self._admins

    @property
    def name(self):
        return self.path.name if self.path else DEFAULT_FILE

    @classmethod
    def from_config(cls, config, config_path):
        """Return the Directory named by config.toml's [directory] section
        (not yet loaded). Exits on a config mistake."""
        if "users" in config or "admin" in config:
            raise SystemExit(f"[users] and [admin] now go in their own file ({DEFAULT_FILE} next to "
                             f"{Path(config_path).name}), which the bot reloads while running. Move "
                             f"them there; see users.example.toml.")
        section = config.get("directory", {})
        if not isinstance(section, dict) or set(section) - DIRECTORY_KEYS:
            raise SystemExit(f"[directory] may only set {' and '.join(sorted(DIRECTORY_KEYS))}.")
        file = section.get("file", DEFAULT_FILE)
        if not isinstance(file, str) or not file:
            raise SystemExit("[directory] file must be a file name or path.")
        seconds = section.get("reload_seconds", DEFAULT_RELOAD_SECONDS)
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds < 0:
            raise SystemExit("[directory] reload_seconds must be a number of seconds, or 0 to only "
                             "reload on request.")
        path = Path(config_path).parent / Path(file).expanduser()
        return cls(path=path, reload_seconds=seconds)

    def load(self):
        """Read the file at startup. Returns False if it doesn't exist yet
        (it is picked up once created); exits if it is invalid."""
        try:
            self.check(force=True)
        except DirectoryError as e:
            if self._seen is None:
                return False
            raise SystemExit(f"{self.path}: {e}") from None
        return True

    def _signature(self):
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return None
        return st.st_mtime_ns, st.st_size, st.st_ino

    def check(self, force=False):
        """Reload the file if it changed, returning a summary of the changes,
        or None if there was nothing new to read. See _check."""
        try:
            summary = self._check(force)
        except DirectoryError as e:
            self.problem = (time.time(), str(e))
            raise
        if summary is not None:
            self.loaded, self.problem = time.time(), None
        return summary

    def _check(self, force):
        """Reload the file if it changed, returning a summary of the changes,
        or None if there was nothing new to read.

        Without force, a change is acted on only once the file has looked the
        same on two checks in a row, so an editor's half-written save isn't
        read. Raises DirectoryError (once per bad version) if the file is
        missing or invalid; the current users then stay in effect.
        """
        signature = self._signature()
        if not force:
            if signature == self._seen:
                self._pending = _NOTHING
                return None
            if signature != self._pending:
                self._pending = signature
                return None
        self._pending = _NOTHING
        self._seen = signature
        if signature is None:
            raise DirectoryError("file not found")
        try:
            with open(self.path, "rb") as f:
                users, admins = parse(tomllib.load(f))
        except tomllib.TOMLDecodeError as e:
            raise DirectoryError(f"not valid TOML: {e}") from None
        except OSError as e:
            raise DirectoryError(f"can't be read: {e.strerror}") from None
        summary = summarize(self._users, self._admins, users, admins)
        self._users, self._admins = users, admins
        for listener in self.on_change:
            listener(summary)
        return summary

    def save_user(self, key, settings):
        """Write one user's settings to the users file, adding the user if
        new, and reload it. Returns the reload summary.

        The result is read back before it is saved: if the file would hold
        anything but its current users with this one change (a section the
        bot can't rewrite cleanly), nothing is written and DirectoryError
        says to edit the file by hand.
        """
        return self._write({key: dict(settings)})

    def save_users(self, changes):
        """save_user for several users at once ({key: settings}), with one
        backup and one reload."""
        return self._write({key: dict(settings) for key, settings in changes.items()})

    def remove_user(self, key):
        """Remove one user's section from the users file and reload it.
        Returns the reload summary. Checked like save_user."""
        return self._write({key: None})

    def _write(self, changes):
        """Write {key: settings, or None to remove the user} and reload."""
        def changed(users):
            users = dict(users)
            for key, settings in changes.items():
                if settings is None:
                    users.pop(key, None)
                else:
                    users[key] = settings
            return users

        if self.path is None:  # not kept in a file (tests)
            old = self._users
            self._users = changed(old)
            summary = summarize(old, self._admins, self._users, self._admins)
            for listener in self.on_change:
                listener(summary)
            return summary
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            text = ""
        except OSError as e:
            raise DirectoryError(f"can't be read: {e.strerror}") from None
        try:
            users, admins = parse(tomllib.loads(text))
        except tomllib.TOMLDecodeError as e:
            raise DirectoryError(f"not valid TOML: {e}; fix it first") from None
        try:
            new_text = text
            for key, settings in changes.items():
                new_text = with_user(new_text, key, settings)
            written = parse(tomllib.loads(new_text))
        except (ValueError, DirectoryError):  # TOMLDecodeError is a ValueError
            written = None
        if written != (changed(users), admins):
            who = ", ".join(possessive(describe(key, users)) for key in changes)
            raise DirectoryError(f"can't be changed automatically; edit {who} section by hand")
        # Keep the version being replaced, then replace the file in one step,
        # keeping its permissions.
        mode = self.path.stat().st_mode & 0o777 if text else 0o600
        if text:
            self._back_up(text, mode)
        temp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        with open(fd, "w", encoding="utf-8") as f:
            f.write(new_text)
        os.chmod(temp, mode)
        os.replace(temp, self.path)
        return self.check(force=True)

    def _back_up(self, text, mode):
        """Save text (the file as it is) in the backups folder next to it,
        as e.g. users-20261020-221500.toml, keeping the newest BACKUPS."""
        folder = self.path.parent / BACKUP_FOLDER
        folder.mkdir(mode=0o700, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = folder / f"{self.path.stem}-{stamp}{self.path.suffix}"
        count = 1
        while backup.exists():  # more than one write in a second
            count += 1
            backup = folder / f"{self.path.stem}-{stamp}-{count}{self.path.suffix}"
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with open(fd, "w", encoding="utf-8") as f:
            f.write(text)
        old = sorted(folder.glob(f"{self.path.stem}-*{self.path.suffix}"), key=lambda p: p.stat().st_mtime_ns)
        for path in old[:-BACKUPS]:
            path.unlink()

    async def watch(self, wake, on_error):
        """Check the file every reload_seconds (or only when woken, if 0)
        and whenever `wake` (an asyncio.Event) is set, which forces a reload.
        on_error(reason) is called when a new version can't be used."""
        while True:
            try:
                await asyncio.wait_for(wake.wait(), self.reload_seconds or None)
            except TimeoutError:
                pass
            forced = wake.is_set()
            wake.clear()
            try:
                self.check(force=forced)
            except DirectoryError as e:
                on_error(str(e))
