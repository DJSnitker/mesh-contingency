"""Managing users over the mesh.

Admins: users lists them, whois shows one, remove takes someone out of the
users file, resetpass clears a forgotten passphrase. Names are radios' names,
kept up to date by the bot, so there is nothing to rename.
Users: whoami shows what the bot knows about you, leave takes you out.

remove, resetpass and leave can't be undone, so each only says what it would
do until the same command is sent again within CONFIRM_SECONDS. Nobody can be
made an admin over the mesh: [admin] keys is only changed by editing the file.
"""

from ..api import CONFIRM_SECONDS, Command, CommandError, CommandResult, Confirmations, pack, page
from ..directory import AmbiguousUser, DirectoryError, describe, find_user, possessive
from .mailbox import FILENAME as MAILBOX
from .mailbox import INBOX_KEY


class UsersBase(Command):
    """Commands that read or change the users file."""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.mailbox = ctx.state.store(MAILBOX)  # fails at startup if the file is unreadable
        self.confirmations = Confirmations()

    def find(self, text):
        """Return (public key, rest of text) for text naming a user; raises
        CommandError if it doesn't."""
        if not text:
            raise CommandError(f"usage: {self.usage}")
        try:
            found = find_user(self.ctx.users, text)
        except AmbiguousUser as e:
            raise CommandError(f"{self.name}: {e}") from None
        if found is None:
            raise CommandError(f"{self.name}: no user {text}")
        return found

    def waiting(self, key):
        """The user's messages in the mailbox."""
        return self.mailbox.data.get(key, [])

    def details(self, key):
        """Everything known about a user, briefly, for whois and whoami."""
        user = self.ctx.users[key]
        parts = [f"{describe(key, self.ctx.users)} ({key[:12]})"]
        if key in self.ctx.admins:
            parts.append("admin")
        parts.append("passphrase set" if user.get(INBOX_KEY) else "no passphrase")
        for setting, value in user.items():
            if setting in ("name", INBOX_KEY):
                continue
            # A list (a group of addresses) as a count, so the reply stays short.
            parts.append(f"{setting} {len(value)} address(es)" if isinstance(value, list) else f"{setting} {value}")
        box = self.waiting(key)
        unread = sum(not entry.get("read") for entry in box)
        parts.append(f"{len(box)} message(s), {unread} unread" if box else "no messages")
        return "; ".join(parts)

    def save(self, key, settings):
        """Write a user's settings (or remove them, if None)."""
        directory = self.ctx.directory
        try:
            if settings is None:
                directory.remove_user(key)
            else:
                directory.save_user(key, settings)
        except DirectoryError as e:
            raise CommandError(f"{self.name}: {directory.name} {e}") from None

    def delete_messages(self, key, which=lambda entry: True):
        """Delete the user's messages that `which` picks; return how many."""
        box = self.waiting(key)
        kept = [entry for entry in box if not which(entry)]
        if kept:
            self.mailbox.data[key] = kept
        else:
            self.mailbox.data.pop(key, None)
        if len(kept) != len(box):
            self.mailbox.save()
        return len(box) - len(kept)

    def ask(self, sender, what, question):
        """None if sender confirmed `what`; otherwise the reply asking them to."""
        if self.confirmations.confirmed(sender.public_key, what):
            return None
        return CommandResult(console="", reply=f"{question} Send it again within {CONFIRM_SECONDS // 60} min "
                                               f"to confirm.", asks=True)


class UsersCommand(UsersBase):
    args = "[page]"
    summary = "List the users and what each has set"

    def entry(self, key):
        user = self.ctx.users[key]
        flags = ["admin"] if key in self.ctx.admins else []
        if user.get(INBOX_KEY):
            flags.append("pass")
        flags += [setting for setting in user if setting not in ("name", INBOX_KEY)]
        return f"{describe(key, self.ctx.users)} {key[:12]}" + (f" ({', '.join(flags)})" if flags else "")

    async def execute(self, text, sender):
        if text and not text.isdigit():
            raise CommandError(f"usage: {self.usage}")
        keys = sorted(self.ctx.users, key=lambda k: describe(k, self.ctx.users).lower())
        if not keys:
            return CommandResult(console="", reply=f"{self.name}: nobody yet")
        messages = pack([f"{self.name} ({len(keys)}):"] + [self.entry(k) for k in keys], separator=" ")
        reply = page(messages, int(text or 1), self.name)
        return CommandResult(console="\n".join(reply), reply=reply)


class WhoisCommand(UsersBase):
    args = "<name or key>"
    summary = "Show what is known about a user"

    async def execute(self, text, sender):
        key, rest = self.find(text)
        if rest:
            raise CommandError(f"{self.name}: no user {text}")
        reply = self.details(key)
        return CommandResult(console=reply, reply=reply)


class RemoveCommand(UsersBase):
    args = "<name or key>"
    summary = "Remove a user and their messages from the node"

    async def execute(self, text, sender):
        key, rest = self.find(text)
        if rest:
            raise CommandError(f"{self.name}: no user {text}")
        name = describe(key, self.ctx.users)
        question = self.ask(sender, key, f"{self.name}: this removes {name} ({key[:12]}) and their "
                                         f"{len(self.waiting(key))} message(s).")
        if question:
            return question
        self.save(key, None)
        deleted = self.delete_messages(key)
        still = "; still an admin (edit [admin] keys to change that)" if key in self.ctx.admins else ""
        reply = f"{self.name}: {name} removed, {deleted} message(s) deleted{still}"
        self.ctx.state.record(self.ctx.name_of(sender), f"removed {name} ({key[:12]}), {deleted} message(s) deleted")
        return CommandResult(console=f"{self.ctx.name_of(sender)}: {reply}", reply=reply)


class ResetPassCommand(UsersBase):
    args = "<name or key>"
    summary = "Clear a user's forgotten passphrase and their sealed messages"

    async def execute(self, text, sender):
        key, rest = self.find(text)
        if rest:
            raise CommandError(f"{self.name}: no user {text}")
        name = describe(key, self.ctx.users)
        sealed = sum("sealed" in entry for entry in self.waiting(key))
        if not self.ctx.users[key].get(INBOX_KEY) and not sealed:
            raise CommandError(f"{self.name}: {name} has no passphrase")
        if sealed:  # nothing to lose otherwise, so no need to ask
            question = self.ask(sender, key, f"{self.name}: this clears {possessive(name)} passphrase and deletes "
                                             f"{sealed} sealed message(s).")
            if question:
                return question
        self.save(key, {k: v for k, v in self.ctx.users[key].items() if k != INBOX_KEY})
        deleted = self.delete_messages(key, lambda entry: "sealed" in entry)
        deleted_text = f"; {deleted} sealed message(s) deleted" if deleted else ""
        self.ctx.send(key, f"An admin cleared your passphrase{deleted_text}. New messages are kept unsealed "
                           f"until you send setpass.")
        reply = f"{self.name}: {possessive(name)} passphrase cleared, {deleted} sealed message(s) deleted"
        self.ctx.state.record(self.ctx.name_of(sender), f"cleared {possessive(name)} passphrase ({key[:12]}), "
                                                        f"{deleted} sealed message(s) deleted")
        return CommandResult(console=f"{self.ctx.name_of(sender)}: {reply}", reply=reply)


class WhoAmICommand(UsersBase):
    summary = "Show what the node knows about you"

    async def execute(self, text, sender):
        if text:
            raise CommandError(f"usage: {self.usage}")
        return CommandResult(console="", reply=self.details(sender.public_key))


class LeaveCommand(UsersBase):
    summary = "Stop being a user; your messages are deleted"

    async def execute(self, text, sender):
        if text:
            raise CommandError(f"usage: {self.usage}")
        key = sender.public_key
        question = self.ask(sender, key, f"{self.name}: this removes you from the users and deletes your "
                                         f"{len(self.waiting(key))} message(s).")
        if question:
            return question
        name = self.ctx.name_of(sender)
        self.save(key, None)
        self.delete_messages(key)
        self.ctx.state.record(name, f"left the users ({key[:12]})")
        still = " You're still an admin." if key in self.ctx.admins else ""
        return CommandResult(console=f"{name} ({key[:12]}) left the users",
                             reply=f"{self.name}: you're no longer a user; send join to ask again.{still}")
