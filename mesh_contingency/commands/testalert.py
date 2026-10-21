"""testalert: post the test message to the alert channel now.

The message, and a weekly time to post it by itself, are set in [alert_test]
in config.toml.
"""

from ..alerts import NoChannelSlot, when_text
from ..api import Command, CommandError, CommandResult


class TestAlertCommand(Command):
    summary = "Post the test message to the alert channel"

    async def execute(self, text, sender):
        if text.strip():
            raise CommandError(f"usage: {self.usage}")
        test = self.ctx.state.alert_test
        if test is None:
            raise CommandError(f"{self.name}: the alert test isn't set up yet")
        if problem := test.problem():
            raise CommandError(f"{self.name}: {problem}")
        try:
            slot, added, messages = await test.send(self.ctx.name_of(sender))
        except NoChannelSlot as e:
            raise CommandError(f"{self.name}: {e}") from None
        channel = test.settings.channel
        where = f"slot {slot}, added to the radio" if added else f"slot {slot}"
        nxt = test.next_time()
        later = f"; next weekly test {when_text(nxt, test.settings.zone)}" if nxt else ""
        console = "\n".join([f"Alert test posted to {channel} ({where}):"] + [f"  {m}" for m in messages])
        return CommandResult(console=console, reply=f"{self.name}: posted to {channel}{later}")
