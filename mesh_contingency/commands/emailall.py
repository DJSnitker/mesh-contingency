"""emailall <message>: email the sender's preconfigured group."""

from .qm import QmCommand


class EmailAllCommand(QmCommand):
    """Same as qm, but each user's config holds a list of addresses."""

    summary = "Email your message to your preset group"
