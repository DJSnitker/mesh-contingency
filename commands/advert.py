"""advert [flood]: make the radio send an advert (admin only)."""

from meshcore import EventType

from .base import ADMIN, Command, CommandError, CommandResult


class AdvertCommand(Command):
    name = "advert"
    usage = "advert [flood]"
    permission = ADMIN

    def __init__(self, radio):
        self.radio = radio  # connected MeshCore instance

    async def execute(self, text, sender):
        mode = text.lower()
        if mode not in ("", "flood"):
            raise CommandError(f"usage: {self.usage}")
        flood = mode == "flood"
        kind = "flood" if flood else "zero-hop"
        res = await self.radio.commands.send_advert(flood=flood)
        if res.type == EventType.ERROR:
            raise RuntimeError(f"radio rejected {kind} advert: {res.payload}")
        return CommandResult(console=f"Sent {kind} advert", reply=f"advert: {kind} sent")
