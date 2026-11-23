"""alert <message>: post a message to MeshCore's Public channel.

The bot takes no commands from channels; this only sends to one. Public is
found by its key, the same on every radio (see alerts.py); the bot never
adds a channel. [alerts] in config.toml posts new weather alerts there by
itself.
"""

from mesh_commands import Command, CommandError, CommandResult

from ..alerts import PUBLIC, NoPublicChannel, message_limit, post, public_slot


class AlertCommand(Command):
    args = "<message>"
    summary = "Post a message to the Public channel"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.radio = ctx.radio  # connected MeshCore instance

    async def execute(self, text, sender):
        message = text.strip()
        if not message:
            raise CommandError(f"usage: {self.usage}")
        limit = message_limit(self.radio)
        if len(message) > limit:
            raise CommandError(f"{self.name}: too long for one channel message ({len(message)} characters; "
                               f"at most {limit}); nothing posted")
        try:
            slot = await public_slot(self.radio)
        except NoPublicChannel as e:
            raise CommandError(f"{self.name}: {e}; nothing posted") from None
        await post(self.radio, slot, [message])
        return CommandResult(console=f"Posted to {PUBLIC} (slot {slot}): {message}",
                             reply=f"{self.name}: posted to {PUBLIC}")
