"""alertmap [county, ST]: look up again the NWS codes of the watched counties.

The automatic alert watcher ([alerts] in config.toml) looks each county's code
up once and keeps it; this redoes it, for every watched county or just one.
"""

from ..alerts import parse_county
from ..api import Command, CommandError, CommandResult


class AlertMapCommand(Command):
    args = "[county, ST]"
    summary = "Look up the NWS codes of the counties watched for weather alerts again"

    async def execute(self, text, sender):
        watcher = self.ctx.state.alert_watcher
        if watcher is None:
            raise CommandError(f"{self.name}: no counties are watched; set counties in [alerts] in config.toml")
        wanted = None
        if text.strip():
            try:
                county = parse_county(text)
            except ValueError as e:
                raise CommandError(f"{self.name}: {e}; usage: {self.usage}") from None
            wanted = [c for c in watcher.settings.counties if c.lower() == county.lower()]
            if not wanted:
                raise CommandError(f"{self.name}: {county} isn't watched; watched: "
                                   f"{'; '.join(watcher.settings.counties)}")
        results = await watcher.map_counties(wanted)
        lines = [f"{county}: {code}" if code else f"{county}: not looked up ({why})" for county, code, why in results]
        done = [county for county, code, _ in results if code]
        if done:
            self.ctx.state.record(self.ctx.name_of(sender), f"looked up the NWS codes of {'; '.join(done)}")
        # The watcher prints each county's code itself.
        return CommandResult(console="", reply=[f"{self.name}: {line}" for line in lines])
