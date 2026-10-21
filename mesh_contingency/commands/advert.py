"""advert [flood]: make the radio send an advert."""

from meshcore import EventType

from ..api import Command, CommandError, CommandResult
from ..console import ADVERTS_FILE, record_advert


class AdvertCommand(Command):
    args = "[flood]"
    summary = "Make the radio advertise itself (flood: across the whole mesh)"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.radio = ctx.radio  # connected MeshCore instance
        self.advert_times = ctx.state.store(ADVERTS_FILE)  # so [advert] every_hours counts this one

    async def execute(self, text, sender):
        mode = text.lower()
        if mode not in ("", "flood"):
            raise CommandError(f"usage: {self.usage}")
        flood = mode == "flood"
        kind = "flood" if flood else "zero-hop"
        res = await self.radio.commands.send_advert(flood=flood)
        if res.type == EventType.ERROR:
            raise RuntimeError(f"radio rejected {kind} advert: {res.payload}")
        record_advert(self.advert_times, flood)
        return CommandResult(console=f"Sent {kind} advert", reply=f"advert: {kind} sent")
