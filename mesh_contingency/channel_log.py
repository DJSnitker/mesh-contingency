"""The radio's channel messages since the bot started, for the web console.

The bot fetches every message the radio holds; the channel ones arrive as
CHANNEL_MSG_RECV events with the channel's slot and the text as the sender
wrote it, "<their name>: <message>". The bot's own posts (alert, comm, the
automatic alerts, the weekly test) don't come back from the radio, so post()
adds them here as it sends them.

Kept in memory only, the newest KEEP of each slot: a restart forgets them,
and nothing of other people's channel traffic is written to disk.
"""

import time
from collections import deque

KEEP = 200  # messages kept per channel slot


def split_sender(text):
    """(sender, message) for a channel message's text; sender is None if it
    doesn't start with "<name>: "."""
    sender, colon, message = text.partition(": ")
    if not colon or not sender.strip():
        return None, text
    return sender, message


class ChannelLog:
    def __init__(self, keep=KEEP):
        self.keep = keep
        self._slots = {}  # slot -> deque of messages, oldest first

    def _add(self, slot, entry):
        self._slots.setdefault(slot, deque(maxlen=self.keep)).append(entry)

    def heard(self, payload, when=None):
        """Add a CHANNEL_MSG_RECV event's payload, heard now (or at when)."""
        if "channel_idx" not in payload:
            return
        sender, message = split_sender(payload.get("text", ""))
        hops = payload.get("path_len")
        self._add(payload["channel_idx"], {
            "time": time.time() if when is None else when, "sender": sender, "text": message,
            # 255 is how the radio says it came direct, through no repeater.
            "hops": 0 if hops == 255 else hops, "snr": payload.get("SNR"), "own": False})

    def sent(self, slot, node_name, text, when=None):
        """Add a message this node posted to a slot, now (or at when)."""
        self._add(slot, {"time": time.time() if when is None else when, "sender": node_name, "text": text,
                         "hops": None, "snr": None, "own": True})

    def messages(self, slot):
        """The slot's messages, newest first."""
        return list(reversed(self._slots.get(slot, ())))

    def summary(self, slot):
        """(how many messages are kept, time.time() of the newest or None)."""
        kept = self._slots.get(slot)
        return (len(kept), kept[-1]["time"]) if kept else (0, None)
