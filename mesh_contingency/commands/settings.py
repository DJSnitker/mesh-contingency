"""Users changing their own email addresses, which are saved to their
section of the users file:

    setqm <address>   the one address qm sends to
    addgroup <address>     add an address to the list emailall sends to
    cleargroup             empty that list

Each command reads and writes the key of the command it serves, set with
`command = "<name>"` in its config entry (qm or emailall by default).

Admins set anyone's, as the console's Users page does:

    setemail <name or key> qm [address] group [address ...]

Either part may be left out; a part with no address clears it. The user is
told what changed.
"""

from ..api import Command, CommandError, CommandResult
from ..directory import AmbiguousUser, DirectoryError, describe, find_user, possessive
from .mail import ADDRESS_RE

# Addresses in a group at most.
MAX_GROUP = 10


class SettingsCommand(Command):
    """Commands that change the sender's own section of the users file."""

    default_setting = ""

    def __init__(self, ctx):
        super().__init__(ctx)
        self.setting = ctx.options.get("command", self.default_setting)

    def addresses(self, sender):
        """The sender's addresses for the setting, as a list."""
        value = self.ctx.users[sender.public_key].get(self.setting)
        return [value] if isinstance(value, str) else list(value or [])

    def save(self, sender, value):
        """Save the sender's setting (removed if value is None) and reload."""
        directory = self.ctx.directory
        settings = dict(self.ctx.users[sender.public_key])
        if value is None:
            settings.pop(self.setting, None)
        else:
            settings[self.setting] = value
        try:
            directory.save_user(sender.public_key, settings)
        except DirectoryError as e:
            raise CommandError(f"{self.name}: {directory.name} {e}") from None

    def address(self, text):
        """The one address in text; raises CommandError if it isn't one."""
        if not text:
            raise CommandError(f"usage: {self.usage}")
        if not ADDRESS_RE.fullmatch(text):
            raise CommandError(f"{self.name}: not an email address: {text}")
        return text


class SetQmCommand(SettingsCommand):
    args = "<address>"
    summary = "Set the address qm sends to; alone, show it"
    default_setting = "qm"

    async def execute(self, text, sender):
        if not text:
            current = self.addresses(sender)
            reply = f"{self.setting}: {', '.join(current)}" if current else f"{self.setting}: no address set"
            return CommandResult(console=reply, reply=reply)
        address = self.address(text)
        self.save(sender, address)
        reply = f"{self.setting} now sends to {address}"
        return CommandResult(console=f"{self.ctx.name_of(sender)}: {reply}", reply=reply)


class AddGroupCommand(SettingsCommand):
    args = "<address>"
    summary = "Add an address to the group emailall sends to; alone, list them"
    default_setting = "emailall"

    async def execute(self, text, sender):
        group = self.addresses(sender)
        if not text:
            reply = f"{self.setting}: {', '.join(group)}" if group else f"{self.setting}: no addresses"
            return CommandResult(console=reply, reply=reply)
        address = self.address(text)
        if address.lower() in (a.lower() for a in group):
            raise CommandError(f"{self.name}: {address} is already in the group")
        if len(group) >= MAX_GROUP:
            raise CommandError(f"{self.name}: the group is full ({MAX_GROUP}); cleargroup to start again")
        self.save(sender, group + [address])
        reply = f"{self.name}: {address} added ({len(group) + 1} in the group)"
        return CommandResult(console=f"{self.ctx.name_of(sender)}: {reply}", reply=reply)


class ClearGroupCommand(SettingsCommand):
    summary = "Remove every address from the group emailall sends to"
    default_setting = "emailall"

    async def execute(self, text, sender):
        if text:
            raise CommandError(f"usage: {self.usage}")
        count = len(self.addresses(sender))
        if count:
            self.save(sender, None)
        reply = f"{self.name}: removed {count} address(es)"
        return CommandResult(console=f"{self.ctx.name_of(sender)}: {reply}", reply=reply)


class SetEmailCommand(Command):
    """An admin setting a user's qm address and emailall group. The keys it
    writes are set with qm = "<name>" and group = "<name>" in its config
    entry (qm and emailall by default)."""

    args = "<name or key> qm [address] group [address ...]"
    summary = "Set a user's qm address and emailall group; no address clears it"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.settings = {"qm": ctx.options.get("qm", "qm"), "group": ctx.options.get("group", "emailall")}

    def parse(self, text):
        """(key, {"qm"/"group": [addresses]}) for text; raises CommandError."""
        if not text:
            raise CommandError(f"usage: {self.usage}")
        try:
            found = find_user(self.ctx.users, text)
        except AmbiguousUser as e:
            raise CommandError(f"{self.name}: {e}") from None
        if found is None:
            raise CommandError(f"{self.name}: no user {text}")
        key, rest = found
        parts, part = {}, None
        for word in rest.split():
            if word.lower() in self.settings:
                part = word.lower()
                if part in parts:
                    raise CommandError(f"{self.name}: {part} given twice")
                parts[part] = []
            elif part is None:
                raise CommandError(f"usage: {self.usage}")
            elif not ADDRESS_RE.fullmatch(word):
                raise CommandError(f"{self.name}: not an email address: {word}")
            elif word.lower() not in (a.lower() for a in parts[part]):
                parts[part].append(word)
        if not parts:
            raise CommandError(f"usage: {self.usage}")
        if len(parts.get("qm", [])) > 1:
            raise CommandError(f"{self.name}: qm takes one address")
        if len(parts.get("group", [])) > MAX_GROUP:
            raise CommandError(f"{self.name}: a group holds at most {MAX_GROUP} addresses")
        return key, parts

    async def execute(self, text, sender):
        key, parts = self.parse(text)
        settings = dict(self.ctx.users[key])
        said = []
        for part, addresses in parts.items():
            setting = self.settings[part]
            if not addresses:
                settings.pop(setting, None)
                said.append(f"{setting} cleared")
            elif part == "qm":
                settings[setting] = addresses[0]
                said.append(f"{setting} {addresses[0]}")
            else:
                settings[setting] = addresses
                said.append(f"{setting} {', '.join(addresses)}")
        directory = self.ctx.directory
        try:
            directory.save_user(key, settings)
        except DirectoryError as e:
            raise CommandError(f"{self.name}: {directory.name} {e}") from None
        name = describe(key, self.ctx.users)
        changes = "; ".join(said)
        self.ctx.send(key, f"An admin changed your email addresses: {changes}")
        reply = f"{self.name}: {possessive(name)} {changes}"
        self.ctx.state.record(self.ctx.name_of(sender), f"set {possessive(name)} {changes} ({key[:12]})")
        return CommandResult(console=f"{self.ctx.name_of(sender)}: {reply}", reply=reply)
