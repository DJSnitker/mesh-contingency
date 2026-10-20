"""roster: everyone who has direct-messaged the node since the bot started."""

import time

from ..api import Command, CommandError, CommandResult


class RosterCommand(Command):
    summary = "Who has messaged this node since it started"

    async def execute(self, text, sender):
        if text:
            raise CommandError(f"usage: {self.usage}")
        state = self.ctx.state
        since = time.strftime("%b %d %H:%M", time.localtime(state.started))
        # Most recent first; the sender asking is one of them.
        names = [name for name, _ in reversed(state.seen.values())]
        reply = f"{self.name} since {since} ({len(names)})" + (f": {', '.join(names)}" if names else "")
        return CommandResult(console=reply, reply=reply)
