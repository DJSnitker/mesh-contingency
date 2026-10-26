"""The web console's direct conversations with contacts, since the bot started.

Only the console's side of the mesh: the messages the console sends a
contact (each sending, then delivered or not) and the contact's replies to
them. A reply is a message from a contact the console messaged within
REPLY_HOURS that isn't a command they may run; the bot keeps it here instead
of answering "unknown command". Commands sent to the node, and the node's
answers, are never kept: they're the sender's business, not the console's.

Kept in memory only, the newest KEEP per contact: a restart forgets them,
and nothing is written to disk. Each contact also counts the replies heard
since the bot started, for the console's unread counts.
"""

import itertools
import time
from collections import deque

KEEP = 200  # messages kept per contact
REPLY_HOURS = 24  # how long after the console's last message a reply is the console's

SENDING, DELIVERED, NOT_DELIVERED = "sending", "delivered", "not delivered"


class Conversations:
    def __init__(self, keep=KEEP):
        self.keep = keep
        self._chats = {}  # full key -> deque of messages, oldest first
        self._heard = {}  # full key -> replies heard since the bot started
        self._last_sent = {}  # full key -> time.time() the console last messaged them
        self._ids = itertools.count(1)

    def _add(self, key, entry):
        self._chats.setdefault(key, deque(maxlen=self.keep)).append(entry)
        return entry

    def sent(self, key, text, when=None):
        """Add a message the console is sending the contact; returns it, for
        delivered() once the radio says."""
        when = time.time() if when is None else when
        self._last_sent[key] = when
        return self._add(key, {"id": next(self._ids), "time": when, "text": text, "own": True,
                               "status": SENDING, "hops": None, "snr": None})

    @staticmethod
    def delivered(entry, ok):
        """The radio acknowledged the message (ok) or gave up on it."""
        entry["status"] = DELIVERED if ok else NOT_DELIVERED

    def expecting(self, key, now=None):
        """Whether a message from the contact now would be a reply to the console."""
        last = self._last_sent.get(key)
        return last is not None and (time.time() if now is None else now) - last <= REPLY_HOURS * 3600

    def replied(self, key, text, hops=None, snr=None, when=None):
        """Add the contact's reply to the console."""
        self._heard[key] = self._heard.get(key, 0) + 1
        self._add(key, {"id": next(self._ids), "time": time.time() if when is None else when, "text": text,
                        # 255 is how the radio says it came direct, through no repeater.
                        "own": False, "status": None, "hops": 0 if hops == 255 else hops, "snr": snr})

    def messages(self, key):
        """The contact's messages, newest first."""
        return [dict(m) for m in reversed(self._chats.get(key, ()))]

    def heard_count(self, key):
        """Replies heard from the contact since the bot started, however many are kept."""
        return self._heard.get(key, 0)

    def keys(self):
        """The contacts with a conversation, the most recent first."""
        return sorted(self._chats, key=lambda k: self._chats[k][-1]["time"], reverse=True)

    def last(self, key):
        """The newest message with the contact, or None."""
        chat = self._chats.get(key)
        return dict(chat[-1]) if chat else None
