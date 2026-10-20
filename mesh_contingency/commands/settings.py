"""Users changing their own email addresses, which are saved to their
section of the users file:

    setquickim <address>   the one address quickim sends to
    addgroup <address>     add an address to the list emailall sends to
    cleargroup             empty that list

Each command reads and writes the key of the command it serves, set with
`command = "<name>"` in its config entry (quickim or emailall by default).
"""

from ..api import Command, CommandError, CommandResult
from ..directory import DirectoryError
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


class SetQuickImCommand(SettingsCommand):
    args = "<address>"
    summary = "Set the address quickim sends to; alone, show it"
    default_setting = "quickim"

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
