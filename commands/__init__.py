"""Registry of mesh commands. To add one, create a Command subclass in its own
module and add an instance in build_commands() below."""

from .advert import AdvertCommand
from .base import ADMIN, PUBLIC, USER, Command, CommandError, CommandResult, Sender
from .notify_default import NotifyDefaultCommand
from .notify_email import NotifyEmailCommand
from .notify_group import NotifyGroupCommand
from .wx import WxCommand


def _normalize_key(key):
    """Reduce a pubkey or prefix to the lowercase 6-byte prefix MeshCore
    includes with direct messages."""
    return key.strip().lower()[:12]


def load_users(config):
    """Return {pubkey prefix: settings} from the [users.<key>] config sections.

    Having a section is what approves a user for USER commands.
    """
    return {_normalize_key(key): user for key, user in config.get("users", {}).items()}


def load_admins(config):
    """Return the set of pubkey prefixes in [admin] keys, allowed ADMIN commands."""
    return {_normalize_key(key) for key in config.get("admin", {}).get("keys", [])}


def build_commands(config, radio):
    """Return {name: Command} for every command, configured from the config
    dict; radio is the connected MeshCore instance."""
    users = load_users(config)
    commands = [
        WxCommand(),
        NotifyDefaultCommand(users),
        NotifyGroupCommand(users),
        NotifyEmailCommand(),
        AdvertCommand(radio),
    ]
    return {cmd.name: cmd for cmd in commands}


__all__ = [
    "build_commands", "load_admins", "load_users",
    "ADMIN", "PUBLIC", "USER", "Command", "CommandError", "CommandResult", "Sender",
]
