"""testalert: post the test message to the Public channel now.

The message, and a weekly time to post it by itself, are set in [alert_test]
in config.toml.
"""

from mesh_commands import Command, CommandError, CommandResult

from ..alerts import PUBLIC, NoPublicChannel, when_text


class TestAlertCommand(Command):
    summary = "Post the test message to the Public channel"

    async def execute(self, text, sender):
        if text.strip():
            raise CommandError(f"usage: {self.usage}")
        test = self.ctx.extras["state"].alert_test
        if test is None:
            raise CommandError(f"{self.name}: the alert test isn't set up yet")
        if problem := test.problem():
            raise CommandError(f"{self.name}: {problem}")
        try:
            slot, messages = await test.send()
        except NoPublicChannel as e:
            raise CommandError(f"{self.name}: {e}; nothing posted") from None
        nxt = test.next_time()
        later = f"; next weekly test {when_text(nxt, test.settings.zone)}" if nxt else ""
        console = "\n".join([f"Alert test posted to {PUBLIC} (slot {slot}):"] + [f"  {m}" for m in messages])
        return CommandResult(console=console, reply=f"{self.name}: posted to {PUBLIC}{later}")
