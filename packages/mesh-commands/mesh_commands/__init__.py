"""Direct-message commands for MeshCore bots.

A command is a Command subclass or a function, enabled per command in a
[commands] config table; the Dispatcher checks who may run it, runs it with
a time limit and fits its reply into mesh messages; MeshLink connects all
that to a meshcore.MeshCore radio. See the README.
"""

from .command import (
    DEFAULT_TIMEOUT,
    Command,
    CommandResult,
    Confirmations,
    Context,
    FunctionCommand,
    Sender,
    command,
)
from .dispatch import UNRECOGNIZED_REPLY, Dispatcher
from .errors import CommandError
from .limits import Limits, describe_rate
from .permissions import ADMIN, DISABLED, LEVELS, PUBLIC, USER, KeyRoles, Roles, is_authorized
from .radio import MeshLink
from .registry import Registry
from .replies import MAX_PARTS, MAX_REPLY_LEN, fit_reply, pack, page, split_reply, to_messages

__version__ = "0.1.0"

__all__ = [
    "ADMIN", "DEFAULT_TIMEOUT", "DISABLED", "LEVELS", "MAX_PARTS", "MAX_REPLY_LEN", "PUBLIC", "UNRECOGNIZED_REPLY",
    "USER", "Command", "CommandError", "CommandResult", "Confirmations", "Context", "Dispatcher", "FunctionCommand",
    "KeyRoles", "Limits", "MeshLink", "Registry", "Roles", "Sender", "command", "describe_rate", "fit_reply",
    "is_authorized", "pack", "page", "split_reply", "to_messages",
]
