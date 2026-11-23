"""Reading config.toml: the admins, and settings older versions had.

Admins are listed in config.toml:

    [admins]
    keys = ["<64 hex digits>", ...]   # each admin radio's full public key

They may send the admin commands (alert, testalert, help). Editing the list
takes effect when the bot restarts.

Before 1.0 the admins were in users.toml ([admin] keys). If config.toml has
no [admins], they're still read from there, with a warning to move them.
Sections and settings for features that were removed (see the tag
archive/full-system) are ignored with one warning, so an upgraded node
keeps running until its config is tidied.
"""

import re
import tomllib
from pathlib import Path

from mesh_commands import Limits, Registry

KEY_RE = re.compile(r"[0-9a-f]{64}")
ADMINS_KEYS = {"keys"}
OLD_USERS_FILE = "users.toml"
# Sections of features removed in 1.0.
RETIRED_SECTIONS = ("backup", "console", "contacts", "directory", "watch")
# Settings removed from sections that are still used.
RETIRED_SETTINGS = {"limits": ("emails_per_day", "emails_per_day_total")}
# Commands removed in 1.0 (rename long before): a config that still lists
# them gets one warning rather than failing to start.
RETIRED_COMMANDS = frozenset({
    "addgroup", "advert", "alertmap", "approve", "area", "backup", "checkins", "clearinbox", "cleargroup",
    "clearstatus", "comm", "contact", "contacts", "deny", "email", "emailall", "health", "history", "inbox",
    "join", "leave", "msg", "ok", "qm", "quickim", "radio", "reload", "remove", "rename", "resetpass", "roster",
    "setemail", "setpass", "setqm", "setquickim", "settings", "status", "users", "verse", "whoami", "whois", "wx",
})
# Where commands are found: this package registers its own there, and any
# installed package can add more.
ENTRY_POINT_GROUP = "mesh_contingency.commands"


def load_config(path):
    """Return the parsed TOML config, or {} if the file does not exist."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def check_keys(keys, where):
    """The keys as a frozenset of lowercase hex, or exit naming the problem."""
    if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
        raise SystemExit(f"{where} keys must be a list of public keys, e.g. keys = [\"{'d0' * 32}\"].")
    found = set()
    for key in keys:
        key = key.strip().lower()
        if not KEY_RE.fullmatch(key):
            raise SystemExit(f"{where} keys: {key[:16]!r}... is not a full public key (64 hex digits).")
        found.add(key)
    return frozenset(found)


def old_users_file(config, config_path):
    """Where an older version kept the users and admins."""
    name = config.get("directory", {}).get("file", OLD_USERS_FILE) if isinstance(config.get("directory"), dict) \
        else OLD_USERS_FILE
    return Path(config_path).resolve().parent / name


def load_admins(config, config_path):
    """Return (admin keys, warnings) from [admins] in config.toml, or from
    an older version's users file if there is no [admins]. Exits on a
    mistake."""
    old = old_users_file(config, config_path)
    if "admins" in config:
        section = config["admins"]
        if not isinstance(section, dict) or set(section) - ADMINS_KEYS:
            raise SystemExit("[admins] may only set keys.")
        warnings = [f"{old.name} is no longer used; delete it once [admins] has every admin."] if old.exists() else []
        return check_keys(section.get("keys", []), "[admins]"), warnings
    if not old.exists():
        return frozenset(), []
    try:
        with open(old, "rb") as f:
            users = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise SystemExit(f"{old} can't be read for its admins ({e}); put them in [admins] keys in config.toml.") \
            from None
    section = users.get("admin", {})
    keys = check_keys(section.get("keys", []) if isinstance(section, dict) else [], f"{old.name} [admin]")
    return keys, [f"admins read from {old.name}, which is otherwise no longer used: move them to [admins] keys "
                  f"in config.toml."]


def retired_settings(config):
    """A warning listing the config's sections and settings for removed
    features, or None. They're ignored."""
    found = [f"[{name}]" for name in RETIRED_SECTIONS if name in config]
    for section, keys in RETIRED_SETTINGS.items():
        if isinstance(config.get(section), dict):
            found += [f"[{section}] {key}" for key in keys if key in config[section]]
    if not found:
        return None
    return (f"config.toml has settings for removed features, ignored: {', '.join(found)}. "
            "Remove them (see config.example.toml).")


def load_commands(config, available=None):
    """The Registry of the commands config.toml enables (installed commands
    are discovered unless `available` gives them). Exits on a mistake."""
    if "permissions" in config:
        raise SystemExit("The [permissions] table is replaced by one [commands.<name>] section "
                         "per command, e.g. [commands.alert] permission = \"admin\"; "
                         "see config.example.toml.")
    limits = Limits.from_config(config, ignore=RETIRED_SETTINGS["limits"])
    return Registry(config, ENTRY_POINT_GROUP, available=available, limits=limits, retired=RETIRED_COMMANDS)
