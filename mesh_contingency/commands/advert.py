"""advert [zero]: make the node's radio advert now, so radios find it.

A flood advert (the default) is relayed across the mesh; `advert zero` is a
zero-hop advert, heard only by radios in direct range. It counts towards
[advert] every_hours, like one sent with SIGUSR1, so the schedule doesn't
send another right after.
"""

from mesh_commands import Command, CommandError

from ..console import ADVERTS_FILE, send_advert

KINDS = {"": True, "flood": True, "zero": False, "zerohop": False, "zero-hop": False}


class AdvertCommand(Command):
    args = "[zero]"
    summary = "Send a flood advert now (zero: only to radios in direct range)"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.radio = ctx.radio  # connected MeshCore instance

    async def execute(self, text, sender):
        kind = text.strip().lower()
        if kind not in KINDS:
            raise CommandError(f"usage: {self.usage}")
        flood = KINDS[kind]
        state = self.ctx.extras.get("state")
        store = state.store(ADVERTS_FILE) if state is not None else None
        if not await send_advert(self.radio, flood, f"advert from {sender.name}", store):
            raise CommandError(f"{self.name}: the radio refused the advert; try again")
        return f"{self.name}: sent a {'flood' if flood else 'zero-hop'} advert"
