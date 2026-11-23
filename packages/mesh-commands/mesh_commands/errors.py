"""The one exception commands raise on purpose."""


class CommandError(Exception):
    """A failure whose message is safe and short enough to reply with."""
