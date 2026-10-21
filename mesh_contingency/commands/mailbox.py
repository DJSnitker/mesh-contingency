"""A mailbox on the node: msg <name> <text> leaves a message for a user,
inbox shows the sender's messages, and clearinbox deletes the ones they have
been shown.

Only users (people in the users file) can be written to. Messages are kept in
mailbox.json next to config.toml until cleared, so they survive a restart and
can be read again if a reply is lost on the air.

Messages older than keep_days (set in [commands.msg], 30 by default, 0 for
never) are deleted, read or not. msg tells the recipient by direct message
that something is waiting, at most once per NOTICE_SECONDS, unless
[commands.msg] sets notify = false.

A user who sets a passphrase with setpass gets their new messages sealed (see
sealing.py): mailbox.json then holds only who sent each one and when, and
inbox <passphrase> opens them. Without a passphrase, messages are kept as
plain text and inbox shows them.
"""

import asyncio
import time

from ..api import CONFIRM_SECONDS, MAX_PARTS, Command, CommandError, CommandResult, split_reply
from ..directory import AmbiguousUser, DirectoryError, describe, find_user, possessive, unquote
from ..sealing import MIN_LENGTH, SealError, check_passphrase, new_inbox_key, open_sealed, seal, unlock
from ..state import ago

FILENAME = "mailbox.json"
# Messages kept for one person at most; more are refused until they clear some.
MAX_WAITING = 20
# The users file setting holding a user's sealing key.
INBOX_KEY = "inbox_key"
DEFAULT_KEEP_DAYS = 30
# New-message notices to one recipient at most once per this many seconds.
NOTICE_SECONDS = 600


class MailboxBase(Command):
    """Commands that share the messages in mailbox.json."""

    # Message text and passphrases are never printed on the console.
    private = True

    def __init__(self, ctx):
        super().__init__(ctx)
        self.store = ctx.state.store(FILENAME)  # fails at startup if the file is unreadable

    @property
    def boxes(self):
        """{recipient's public key: [{"from", "time", "read", and "text" or
        "sealed"}, ...] oldest first}"""
        return self.store.data

    def inbox_key(self, sender):
        """The sender's sealing key from the users file, or None."""
        return self.ctx.users.get(sender.public_key, {}).get(INBOX_KEY)

    def sibling(self, cls):
        """The loaded command of this class (e.g. MsgCommand), or None."""
        return next((c for c in self.ctx.commands.values() if isinstance(c, cls)), None)

    def expire(self):
        """Delete messages older than msg's keep_days."""
        msg = self.sibling(MsgCommand)
        days = msg.keep_days if msg else DEFAULT_KEEP_DAYS
        if not days:
            return
        cutoff = time.time() - days * 86400
        changed = False
        for key, box in list(self.boxes.items()):
            kept = [entry for entry in box if entry["time"] >= cutoff]
            if len(kept) != len(box):
                changed = True
                if kept:
                    self.boxes[key] = kept
                else:
                    del self.boxes[key]
        if changed:
            self.store.save()


class MsgCommand(MailboxBase):
    args = "<name> <message>"
    summary = "Leave a message for a user; they read it with inbox"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.keep_days = ctx.options.get("keep_days", DEFAULT_KEEP_DAYS)
        if isinstance(self.keep_days, bool) or not isinstance(self.keep_days, int) or self.keep_days < 0:
            raise ValueError("keep_days must be a whole number of days, or 0 to keep messages forever")
        self.notify = ctx.options.get("notify", True)
        if not isinstance(self.notify, bool):
            raise ValueError("notify must be true or false")
        self.notified = {}  # recipient's public key -> time.monotonic() of the last notice

    async def start(self):
        self.expire()

    def tell_recipient(self, key, sender):
        """Let the recipient know a message is waiting, unless they were told
        recently or wrote it themselves."""
        now = time.monotonic()
        recently = now - self.notified.get(key, -NOTICE_SECONDS) < NOTICE_SECONDS
        if not self.notify or key == sender.public_key or recently:
            return
        self.notified[key] = now
        inbox = self.sibling(InboxCommand)
        hint = f"; send {inbox.name} to read" if inbox else ""
        self.ctx.send(key, f"{inbox.name if inbox else self.name}: new message from {self.ctx.name_of(sender)}{hint}")

    async def execute(self, text, sender):
        if not text:
            raise CommandError(f"usage: {self.usage}")
        try:
            found = find_user(self.ctx.users, text)
        except AmbiguousUser as e:
            raise CommandError(f"{self.name}: {e}") from None
        if found is None:
            quoted = unquote(text)
            raise CommandError(f"{self.name}: no user {quoted[0] if quoted else text.split()[0]}; "
                               f"put a name with spaces in « »")
        key, message = found
        name = describe(key, self.ctx.users)
        if not message:
            raise CommandError(f"usage: {self.usage}")
        self.expire()
        box = self.boxes.setdefault(key, [])
        if len(box) >= MAX_WAITING:
            raise CommandError(f"{self.name}: {possessive(name)} inbox is full")
        entry = {"from": self.ctx.name_of(sender), "time": time.time(), "read": False}
        inbox_key = self.ctx.users[key].get(INBOX_KEY)
        if inbox_key:
            try:
                entry["sealed"] = seal(message, inbox_key)
            except SealError:
                raise CommandError(f"{self.name}: {possessive(name)} {INBOX_KEY} is broken; ask an admin") from None
        else:
            entry["text"] = message
        box.append(entry)
        self.store.save()
        self.tell_recipient(key, sender)
        how = "sealed message" if inbox_key else "Message"
        return CommandResult(console=f"{how} for {name} from {self.ctx.name_of(sender)}",
                             reply=f"{self.name}: saved for {name} ({len(box)} in their inbox)")


def pages(items):
    """Split [(entry, text), ...] into pages of whole messages, each page at
    most MAX_PARTS - 1 mesh messages (the last part says what's next).
    Returns a list of [(entry, mesh messages), ...] lists."""
    result, page, size = [], [], 0
    for entry, text in items:
        parts = split_reply(f"{entry['from']} {ago(entry['time'])}: {text}")
        if page and size + len(parts) > MAX_PARTS - 1:
            result.append(page)
            page, size = [], 0
        page.append((entry, parts))
        size += len(parts)
    return result + [page] if page else result


class InboxCommand(MailboxBase):
    args = "[passphrase] [page]"
    summary = "Read the messages left for you; clear them with clearinbox"

    def parse(self, text):
        """Return (passphrase or None, page number) from the command text."""
        words = text.split()
        if not words:
            return None, 1
        # A page number is short; a passphrase is at least MIN_LENGTH long.
        if len(words) == 1 and words[0].isdigit() and len(words[0]) < MIN_LENGTH:
            return None, int(words[0])
        if len(words) == 1:
            return words[0], 1
        if len(words) == 2 and words[1].isdigit():
            return words[0], int(words[1])
        raise CommandError(f"usage: {self.usage}")

    @staticmethod
    def text_of(entry, private):
        """A message's text, opened with the private key if it is sealed."""
        if "sealed" not in entry:
            return entry["text"]
        if private is None:
            return "(sealed, and you have no passphrase now)"
        try:
            return open_sealed(entry["sealed"], private)
        except SealError:
            return "(sealed with another passphrase; can't be opened)"

    def waiting(self, box):
        """Who left the messages and when, without what they say."""
        senders = ", ".join(f"{entry['from']} {ago(entry['time'])}" for entry in box)
        return (f"{self.name}: {len(box)} message(s) from {senders}. "
                f"Send {self.name} <passphrase> to read.")

    async def execute(self, text, sender):
        passphrase, number = self.parse(text)
        self.expire()
        box = self.boxes.get(sender.public_key, [])
        inbox_key = self.inbox_key(sender)
        private = None
        if passphrase is not None:
            if not inbox_key:
                raise CommandError(f"{self.name}: you have no passphrase; send {self.name} alone")
            try:
                private = await asyncio.to_thread(unlock, passphrase, inbox_key)
            except SealError:
                raise CommandError(f"{self.name}: your {INBOX_KEY} is broken; ask an admin") from None
            if private is None:
                raise CommandError(f"{self.name}: wrong passphrase")
        if not box:
            return CommandResult(console="", reply=f"{self.name}: no messages")
        if inbox_key and private is None:
            return CommandResult(console=f"Told {self.ctx.name_of(sender)} {len(box)} message(s) are waiting",
                                 reply=self.waiting(box))
        all_pages = pages([(entry, self.text_of(entry, private)) for entry in box])
        if not 1 <= number <= len(all_pages):
            raise CommandError(f"{self.name}: there are {len(all_pages)} page(s)")
        replies = []
        for entry, parts in all_pages[number - 1]:
            entry["read"] = True
            replies += parts
        if number < len(all_pages):
            again = f"{self.name} <passphrase>" if private is not None else self.name
            replies.append(f"{self.name}: page {number} of {len(all_pages)}; send {again} {number + 1} for more")
        self.store.save()
        return CommandResult(console=f"Showed {self.ctx.name_of(sender)} inbox page {number} of {len(all_pages)}",
                             reply=replies)


class ClearInboxCommand(MailboxBase):
    args = "[all]"
    summary = "Delete the messages inbox has shown you, or with all, every one"
    private = False  # shows no message text

    async def execute(self, text, sender):
        if text.lower() not in ("", "all"):
            raise CommandError(f"usage: {self.usage}")
        box = self.boxes.get(sender.public_key, [])
        # Only what was shown, unless asked, so a message that arrived since
        # isn't lost unread.
        kept = [] if text else [entry for entry in box if not entry.get("read")]
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


class SetPassCommand(MailboxBase):
    args = "<passphrase>"
    summary = "Seal new messages to you; then read them with inbox <passphrase>"

    def __init__(self, ctx):
        super().__init__(ctx)
        # {public key: (new inbox_key, time.monotonic())} for a change waiting
        # to be confirmed. Only the public half is kept, never the passphrase.
        self.pending = {}

    async def matches(self, passphrase, inbox_key):
        """True if the passphrase opens inbox_key (False if it is broken)."""
        try:
            return await asyncio.to_thread(unlock, passphrase, inbox_key) is not None
        except SealError:
            return False

    async def execute(self, text, sender):
        if not text:
            raise CommandError(f"usage: {self.usage}")
        problem = check_passphrase(text)
        if problem:
            raise CommandError(f"{self.name}: a passphrase {problem}")
        key = sender.public_key
        current = self.inbox_key(sender)
        if current and await self.matches(text, current):
            return CommandResult(console="", reply=f"{self.name}: that is already your passphrase")
        box = self.boxes.get(key, [])
        sealed = sum("sealed" in entry for entry in box)
        pending, when = self.pending.pop(key, (None, 0))
        if sealed and not (time.monotonic() - when < CONFIRM_SECONDS and await self.matches(text, pending)):
            # Sealed messages can't be opened with a new passphrase: ask first.
            self.pending[key] = (await asyncio.to_thread(new_inbox_key, text), time.monotonic())
            return CommandResult(
                console=f"{self.ctx.name_of(sender)}: asked to confirm a new passphrase",
                reply=[f"{self.name}: your {sealed} sealed message(s) only open with your old passphrase, "
                       f"and will be deleted.",
                       f"Read them first with inbox <old passphrase>, or send the same setpass again "
                       f"within {CONFIRM_SECONDS // 60} min to confirm."])
        inbox_key = pending if sealed else await asyncio.to_thread(new_inbox_key, text)
        settings = {**self.ctx.users[key], INBOX_KEY: inbox_key}
        directory = self.ctx.directory
        try:
            directory.save_user(key, settings)
        except DirectoryError as e:
            raise CommandError(f"{self.name}: {directory.name} {e}") from None
        replies = [f"{self.name}: passphrase set; new messages to you will be sealed.",
                   "A forgotten passphrase can't be recovered, and messages sealed with it are lost."]
        if sealed:
            kept = [entry for entry in box if "sealed" not in entry]
            if kept:
                self.boxes[key] = kept
            else:
                self.boxes.pop(key, None)
            self.store.save()
            replies.append(f"{self.name}: deleted {sealed} message(s) sealed with the old passphrase.")
        return CommandResult(console=f"{self.ctx.name_of(sender)}: passphrase set", reply=replies)
