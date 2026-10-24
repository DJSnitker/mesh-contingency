"""comm <message>: post a message to the public communications channel.

The bot takes no commands from channels; this only sends to one. The channel is a hashtag
channel (#name), which anyone can join by adding the same name. If the radio
doesn't have it, it is added to the first empty channel slot at startup (and
again when posting, in case it was removed meanwhile). It works as alert does,
on a channel of its own.
"""

from .alert import AlertCommand

COMM_CHANNEL = "#contingency-comm"


class CommCommand(AlertCommand):
    summary = "Post a message to the public communications channel"
    default_channel = COMM_CHANNEL
