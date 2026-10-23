"""alert <message>: post a message to the public alert channel.

The bot takes no commands from channels; this only sends to one. The channel
is a hashtag channel (#name), which anyone can join by adding the same name. If the
radio doesn't have it, it is added to the first empty channel slot at startup
(and again when posting, in case it was removed meanwhile). [alerts] in
config.toml posts new weather alerts to the same channel by itself (see
alerts.py).
"""

from ..alerts import DEFAULT_CHANNEL, NoChannelSlot, channel_slot, check_channel, message_limit, post
from ..api import Command, CommandError, CommandResult


class AlertCommand(Command):
    args = "<message>"
    summary = "Post a message to the public alert channel"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.radio = ctx.radio  # connected MeshCore instance
        self.channel = check_channel(ctx.options.get("channel", DEFAULT_CHANNEL))

    async def channel_slot(self):
        """Return (slot, added): the radio's slot for the channel, adding it if needed."""
        try:
            return await channel_slot(self.radio, self.channel)
        except NoChannelSlot as e:
            raise CommandError(f"{self.name}: {e}") from None

    async def start(self):
        slot, added = await self.channel_slot()
        return f"{self.name}: {self.channel} is channel slot {slot}{' (added to the radio)' if added else ''}."

    async def execute(self, text, sender):
        message = text.strip()
        if not message:
            raise CommandError(f"usage: {self.usage}")
        limit = message_limit(self.radio)
        if len(message) > limit:
            raise CommandError(f"{self.name}: too long for one channel message ({len(message)} characters; "
                               f"at most {limit}); nothing posted")
        slot, added = await self.channel_slot()
        await post(self.radio, slot, [message], self.ctx.state.channel_log)
        self.ctx.state.record(self.ctx.name_of(sender), f"posted to {self.channel}: {message}")
        where = f"slot {slot}, added to the radio" if added else f"slot {slot}"
        return CommandResult(console=f"Posted to {self.channel} ({where}): {message}",
                             reply=f"{self.name}: posted to {self.channel}")
