"""emailall <message>: email the sender's preconfigured group."""

from .quickim import QuickImCommand


class EmailAllCommand(QuickImCommand):
    """Same as quickim, but each user's config holds a list of addresses."""

    summary = "Email your message to your preset group"
