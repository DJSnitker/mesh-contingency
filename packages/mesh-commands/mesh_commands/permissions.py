"""Who may run a command.

Each command gets one level from the config's [commands.<name>] section.
Only direct messages are handled, so a sender is identified by the full
public key of the one radio contact their message came from (or not at all).
Who counts as a user or an admin is up to the project, through a Roles
object; KeyRoles is the simple one, two sets of keys.
"""

from typing import Protocol

PUBLIC = "public"  # anyone who can direct-message the node
USER = "user"  # senders Roles.is_user says yes to
ADMIN = "admin"  # senders Roles.is_admin says yes to
DISABLED = "disabled"  # nobody
LEVELS = (PUBLIC, USER, ADMIN, DISABLED)


class Roles(Protocol):
    def is_user(self, public_key: str) -> bool: ...

    def is_admin(self, public_key: str) -> bool: ...


class KeyRoles:
    """Roles from fixed sets of full public keys (64 lowercase hex)."""

    def __init__(self, users=(), admins=()):
        self.users = frozenset(users)
        self.admins = frozenset(admins)

    def is_user(self, public_key):
        return public_key in self.users

    def is_admin(self, public_key):
        return public_key in self.admins


NO_ROLES = KeyRoles()


def is_authorized(command, sender, roles):
    """Return True if the sender may run the command."""
    if command.permission == PUBLIC:
        return True
    if sender.public_key is None:
        return False
    if command.permission == USER:
        return roles.is_user(sender.public_key)
    if command.permission == ADMIN:
        return roles.is_admin(sender.public_key)
    return False
