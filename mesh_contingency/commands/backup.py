"""backup: make a backup of the bot's data now.

Where backups go, how often they're made by themselves and how many are kept
are set in [backup] in config.toml.
"""

from ..api import Command, CommandError, CommandResult
from ..backup import BackupError


class BackupCommand(Command):
    summary = "Back up the bot's data now"

    async def execute(self, text, sender):
        if text.strip():
            raise CommandError(f"usage: {self.usage}")
        backups = self.ctx.state.backups
        if backups is None:
            raise CommandError(f"{self.name}: backups aren't set up yet")
        try:
            name, copied, _ = await backups.make(self.ctx.name_of(sender))
        except BackupError as e:
            raise CommandError(f"{self.name}: failed, {e}; see the console") from None
        to = backups.settings.to.rstrip("/")
        reply = f"{self.name}: {copied} file(s) saved in {to}/{name}; newest {backups.settings.keep} kept"
        return CommandResult(console="", reply=reply)
