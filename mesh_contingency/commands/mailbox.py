"""A mailbox on the node: msg <name> <text> leaves a message for a user,
inbox shows the sender's messages, and clearinbox deletes the ones they have
been shown.

Only users (people in the users file) can be written to. Messages are kept in
mailbox.json next to config.toml until cleared, so they survive a restart and
can be read again if a reply is lost on the air.
"""

import re
import time

from ..api import MAX_PARTS, Command, CommandError, CommandResult, split_reply
from ..state import ago

FILENAME = "mailbox.json"
# Messages kept for one person at most; more are refused until they clear some.
MAX_WAITING = 20
# A key prefix naming a user: at least 4 hex characters.
KEY_PREFIX_RE = re.compile(r"[0-9a-f]{4,64}")


class MailboxBase(Command):
    """Commands that share the messages in mailbox.json."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.store = ctx.state.store(FILENAME)  # fails at startup if the file is unreadable

    @property
    def boxes(self):
        """{recipient's public key: [{"from", "text", "time", "read"}, ...] oldest first}"""
        return self.store.data


class MsgCommand(MailboxBase):
    args = "<name> <message>"
    summary = "Leave a message for a user; they read it with inbox"

    def recipient(self, text):
        """Return (public key, name, message) for text starting with a
        user's name or key prefix. Raises CommandError if it doesn't."""
        lowered = text.lower()
        named = [(key, user["name"]) for key, user in self.ctx.users.items() if user.get("name")]
        # The longest name that starts the text, so "Ann Lee hi" isn't for "Ann".
        for key, name in sorted(named, key=lambda kn: -len(kn[1])):
            rest = text[len(name):]
            if lowered.startswith(name.lower()) and (not rest or rest[0].isspace()):
                return key, name, rest.strip()
        first, _, message = text.partition(" ")
        if KEY_PREFIX_RE.fullmatch(first.lower()):
            keys = [key for key in self.ctx.users if key.startswith(first.lower())]
            if len(keys) == 1:
                return keys[0], self.ctx.users[keys[0]].get("name") or keys[0][:12], message.strip()
        raise CommandError(f"{self.name}: no user {first}")

    async def execute(self, text, sender):
        if not text:
            raise CommandError(f"usage: {self.usage}")
        key, name, message = self.recipient(text)
        if not message:
            raise CommandError(f"usage: {self.usage}")
        box = self.boxes.setdefault(key, [])
        if len(box) >= MAX_WAITING:
            raise CommandError(f"{self.name}: {name}'s inbox is full")
        box.append({"from": self.ctx.name_of(sender), "text": message, "time": time.time(), "read": False})
        self.store.save()
        return CommandResult(console=f"Message for {name} from {self.ctx.name_of(sender)}: {message}",
                             reply=f"{self.name}: saved for {name} ({len(box)} in their inbox)")


def pages(box):
    """Split a mailbox into pages of whole messages, each page at most
    MAX_PARTS - 1 mesh messages (the last part says what's next). Returns a
    list of [(entry, mesh messages), ...] lists."""
    result, page, size = [], [], 0
    for entry in box:
        parts = split_reply(f"{entry['from']} {ago(entry['time'])}: {entry['text']}")
        if page and size + len(parts) > MAX_PARTS - 1:
            result.append(page)
            page, size = [], 0
        page.append((entry, parts))
        size += len(parts)
    return result + [page] if page else result


class InboxCommand(MailboxBase):
    args = "[page]"
    summary = "Read the messages left for you; clear them with clearinbox"

    async def execute(self, text, sender):
        if text and not text.isdigit():
            raise CommandError(f"usage: {self.usage}")
        all_pages = pages(self.boxes.get(sender.public_key, []))
        if not all_pages:
            return CommandResult(console="", reply=f"{self.name}: no messages")
        number = int(text or 1)
        if not 1 <= number <= len(all_pages):
            raise CommandError(f"{self.name}: there are {len(all_pages)} page(s)")
        replies = []
        for entry, parts in all_pages[number - 1]:
            entry["read"] = True
            replies += parts
        if number < len(all_pages):
            replies.append(f"{self.name}: page {number} of {len(all_pages)}; send {self.name} {number + 1} for more")
        self.store.save()
        return CommandResult(console=f"Showed {self.ctx.name_of(sender)} inbox page {number} of {len(all_pages)}",
                             reply=replies)


class ClearInboxCommand(MailboxBase):
    summary = "Delete the messages inbox has shown you"

    async def execute(self, text, sender):
        if text:
            raise CommandError(f"usage: {self.usage}")
        box = self.boxes.get(sender.public_key, [])
        # Only what was shown, so a message that arrived since isn't lost unread.
        kept = [entry for entry in box if not entry.get("read")]
        deleted = len(box) - len(kept)
        if kept:
            self.boxes[sender.public_key] = kept
        else:
            self.boxes.pop(sender.public_key, None)
        self.store.save()
        reply = f"{self.name}: deleted {deleted} message(s)"
        if kept:
            reply += f"; {len(kept)} new one(s) kept, see inbox"
        return CommandResult(console=f"{self.ctx.name_of(sender)}: {reply}", reply=reply)
