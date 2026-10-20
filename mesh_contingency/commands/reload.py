"""reload: read the users file now instead of waiting for the next check."""

from ..api import Command, CommandError, CommandResult
from ..directory import DirectoryError


class ReloadCommand(Command):
    summary = "Reload the users file now"

    async def execute(self, text, sender):
        directory = self.ctx.directory
        try:
            summary = directory.check(force=True)
        except DirectoryError as e:
            raise CommandError(f"{self.name}: {directory.name} not reloaded: {e}") from None
        # The bot logs every reload itself, so nothing more for the console.
        return CommandResult(console="", reply=f"{self.name}: {summary}")
