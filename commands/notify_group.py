"""notify_group <message>: email a preconfigured list of users."""

from .notify_default import NotifyDefaultCommand


class NotifyGroupCommand(NotifyDefaultCommand):
    """Same as notify_default, but each user's config holds a list of addresses."""

    name = "notify_group"
    usage = "notify_group <message>"
