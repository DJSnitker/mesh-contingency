"""Console users: the people who may log in to the web console from another
computer (the remote console, item 20). They are their own accounts, a name
and a password, with nothing to do with radios: not in users.toml, not
admins over the mesh, and no radio's key can be one.

Kept in console_users.json next to config.toml:

    {"users": [
      {"name": "sam", "password": "scrypt$32768$8$1$<salt>$<hash>",
       "created": 1762790000, "created_by": "node", "changed": 1762790000,
       "last_login": 1762800000}
    ]}

- A name is lowercase (what's typed is lowered first, so names are compared
  without case): 1 to 32 letters, digits, dots, dashes or underscores,
  starting with a letter or digit.
- A password is kept only as a scrypt hash (standard library) with its own
  random salt and cost, so the cost can be raised later. It is never
  printed or kept anywhere else.
- created_by is "node" for a user made with the command on this computer,
  or the console user who made them; changed is when the password was last
  set, so the bot can end that user's sessions when it changes.
- last_login, once they have logged in, is when they last did (the bot
  writes it).
- The file is readable only by this account, written whole (a temporary
  file, then a rename) and under a lock, as the command and the bot may both
  change it. It is left out of backups (backup.py).

The first console user is made on this computer with
mesh-contingency-console user add (users_cli.py).
"""

import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: no lock; the command is meant for the bot's own computer
    fcntl = None

USERS_FILE = "console_users.json"
NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,31}")
NAME_RULE = "1 to 32 letters, digits, dots, dashes or underscores, starting with a letter or digit"
PASSWORD_MIN, PASSWORD_MAX = 12, 128
# scrypt cost: 2**15 with r=8 takes 32 MB and about a tenth of a second.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**15, 8, 1
SALT_BYTES = 16
HASH_BYTES = 32
FIELDS = {"name", "password", "created", "created_by", "changed"}
OPTIONAL_FIELDS = {"last_login"}
BY_NODE = "node"


class ConsoleUsersError(Exception):
    """A console users file that can't be used; the message says why."""


def normal_name(name):
    """name as it's kept: stripped and lowercase."""
    return name.strip().lower()


def check_name(name):
    """Return why a (normalized) name can't be used, or None if it can."""
    return None if NAME_RE.fullmatch(name) else f"a console user's name is {NAME_RULE}"


def check_password(password):
    """Return why a password can't be used, or None if it can."""
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        return f"a password is {PASSWORD_MIN} to {PASSWORD_MAX} characters"
    return None


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def _scrypt(password, salt, n, r, p):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=HASH_BYTES,
                          maxmem=256 * n * r)


def hash_password(password, n=None):
    """The text kept for password: scrypt$n$r$p$salt$hash (base64), at cost n
    (default SCRYPT_N)."""
    n = n or SCRYPT_N
    salt = secrets.token_bytes(SALT_BYTES)
    return "$".join(["scrypt", str(n), str(SCRYPT_R), str(SCRYPT_P), _b64(salt),
                     _b64(_scrypt(password, salt, n, SCRYPT_R, SCRYPT_P))])


def _parse_hash(stored):
    """(n, r, p, salt, hash) from a kept password, or None if it isn't one."""
    parts = stored.split("$") if isinstance(stored, str) else []
    if len(parts) != 6 or parts[0] != "scrypt":
        return None
    try:
        n, r, p = (int(x) for x in parts[1:4])
        salt, digest = base64.b64decode(parts[4], validate=True), base64.b64decode(parts[5], validate=True)
    except ValueError:
        return None
    if n < 2 or n & (n - 1) or not 1 <= r <= 32 or not 1 <= p <= 16 or not salt or len(digest) != HASH_BYTES:
        return None
    return n, r, p, salt, digest


def verify_password(password, stored):
    """True if password is the one kept as stored."""
    parsed = _parse_hash(stored)
    if parsed is None:
        return False
    n, r, p, salt, digest = parsed
    return hmac.compare_digest(_scrypt(password, salt, n, r, p), digest)


def new_user(name, password, created_by=BY_NODE, n=None):
    now = int(time.time())
    return {"name": name, "password": hash_password(password, n), "created": now, "created_by": created_by,
            "changed": now}


def set_password(user, password, n=None):
    """Give user (a kept entry) a new password."""
    user["password"] = hash_password(password, n)
    user["changed"] = max(int(time.time()), user["changed"] + 1)  # always a change the bot can see


def _check_user(entry, where):
    if not isinstance(entry, dict) or not FIELDS <= set(entry) <= FIELDS | OPTIONAL_FIELDS:
        raise ConsoleUsersError(f"{where} must have exactly {', '.join(sorted(FIELDS))} (and maybe "
                                f"{', '.join(sorted(OPTIONAL_FIELDS))})")
    if not isinstance(entry["name"], str) or check_name(entry["name"]):
        raise ConsoleUsersError(f"{where}: name is {NAME_RULE}, in lowercase")
    if _parse_hash(entry["password"]) is None:
        raise ConsoleUsersError(f"{where}: password isn't a kept password; set it again with user password")
    if not isinstance(entry["created_by"], str) or not entry["created_by"]:
        raise ConsoleUsersError(f"{where}: created_by must be who made it")
    for field in ("created", "changed", "last_login"):
        if field not in entry:
            continue
        if isinstance(entry[field], bool) or not isinstance(entry[field], int) or entry[field] < 0:
            raise ConsoleUsersError(f"{where}: {field} must be a whole number")


def parse(data):
    """{name: user} from the file's parsed JSON. Raises ConsoleUsersError."""
    if not isinstance(data, dict) or set(data) != {"users"} or not isinstance(data["users"], list):
        raise ConsoleUsersError('must be {"users": [...]}')
    users = {}
    for i, entry in enumerate(data["users"]):
        _check_user(entry, f"console user {i + 1}")
        if entry["name"] in users:
            raise ConsoleUsersError(f"two console users are called {entry['name']}")
        users[entry["name"]] = entry
    return users


def users_path(config_path):
    return Path(config_path).resolve().parent / USERS_FILE


def load(path):
    """{name: user} from path, {} if there is none. Raises ConsoleUsersError."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise ConsoleUsersError(f"can't be read: {e.strerror or e}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ConsoleUsersError(f"not valid JSON: {e}") from None
    return parse(data)


def save(path, users):
    """Write users ({name: user}) to path, readable only by this account."""
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w", encoding="utf-8") as f:
        json.dump({"users": [users[name] for name in sorted(users)]}, f, indent=2)
        f.write("\n")
    os.replace(temp, path)


@contextlib.contextmanager
def changing(path):
    """Load the console users under a lock, and save them after the block
    (unless it raises): with changing(path) as users: users[...] = ..."""
    path = Path(path)
    lock_fd = os.open(path.with_name(path.name + ".lock"), os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        if fcntl:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        users = load(path)
        yield users
        save(path, users)
    finally:
        os.close(lock_fd)  # also releases the lock
