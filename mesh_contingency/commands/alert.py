"""alert <message>: post a message to the alert channel, MeshCore's Public
channel unless [alerts] channel names another.

The bot takes no commands from channels; this only sends to one, found by
its key (see alerts.py). [alerts] in config.toml posts new weather alerts
there by itself.
"""

from mesh_commands import Command, CommandError, CommandResult

from ..alerts import PUBLIC_CHANNEL, NoChannel, channel_slot, message_limit, post


class AlertCommand(Command):
    args = "<message>"
    summary = "Post a message to the alert channel"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.radio = ctx.radio  # connected MeshCore instance

    @property
    def channel(self):
        """[alerts] channel, which the bot keeps on its state once it's connected."""
        return getattr(self.ctx.extras.get("state"), "channel", None) or PUBLIC_CHANNEL

    async def execute(self, text, sender):
        message = text.strip()
        if not message:
            raise CommandError(f"usage: {self.usage}")
        limit = message_limit(self.radio)
        if len(message) > limit:
            raise CommandError(f"{self.name}: too long for one channel message ({len(message)} characters; "
                               f"at most {limit}); nothing posted")
        try:
            slot = await channel_slot(self.radio, self.channel)
        except NoChannel as e:
            raise CommandError(f"{self.name}: {e}; nothing posted") from None
        await post(self.radio, slot, [message])
        return CommandResult(console=f"Posted to {self.channel} (slot {slot}): {message}",
                             reply=f"{self.name}: posted to {self.channel}")
