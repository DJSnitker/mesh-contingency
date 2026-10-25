"""area [county, ST]: the weather now in the counties the node watches.

area alone lists the counties [alerts] watches; area <county> sends that
county's last report: its alerts, the conditions, the wind, the next
forecast period and how old the report is, in one message. The reports are
the ones the bot keeps (area_weather.py, every 15 min), so asking never
waits on the NWS, and when the internet is down the last report still comes,
with its age.
"""

import time

from ..alerts import county_name, parse_county
from ..api import Command, CommandError, CommandResult
from ..state import ago


def report_line(county, report, alerts, now):
    """One mesh message: the county, then its alerts, conditions, wind, the
    next forecast period and the report's age, as many as fit."""
    sections = []
    events = list(dict.fromkeys(a.get("event") for a in alerts if a.get("event")))
    if events:
        sections.append("ALERT: " + "; ".join(events))
    now_parts = [f"{report['temp_f']:.0f}F" if report.get("temp_f") is not None else None, report.get("text")]
    if report.get("feels_f") is not None and report.get("temp_f") is not None \
            and abs(report["feels_f"] - report["temp_f"]) >= 3:
        now_parts.append(f"feels {report['feels_f']:.0f}F")
    sections.append(", ".join(p for p in now_parts if p) or "no current obs")
    if report.get("wind_mph") is not None:
        wind = f"{report.get('wind_dir') or ''}{report['wind_mph']:.0f}mph"
        if report.get("gust_mph"):
            wind += f" G{report['gust_mph']:.0f}"
        sections.append(wind)
    seen = report.get("observed") or report.get("updated")
    if seen:
        sections.append(ago(seen, now))
    for period in report.get("periods", [])[:1]:
        pop = f" {period['pop']:.0f}%" if period.get("pop") else ""
        sections.append(f"{period['name']}: {period['temp']}{period['unit']} {period['text']}{pop}")
    return Command.fit_reply(county, sections)


class AreaCommand(Command):
    args = "[county, ST]"
    summary = "The weather now in the counties the node watches; alone, list them"
    # Why it's off, for the startup warning.
    unconfigured = "area has no counties to report on: it needs [alerts] counties"

    @property
    def enabled(self):
        watcher = self.ctx.state.alert_watcher
        return bool(watcher and watcher.settings.counties)

    async def execute(self, text, sender):
        area = self.ctx.state.area_weather
        counties = list(area.counties) if area else []
        if not counties:
            raise CommandError(f"{self.name}: no counties are watched")
        if not text:
            reply = self.split_reply(f"{self.name}: {'; '.join(counties)}")
            return CommandResult(console="\n".join(reply), reply=reply)
        county = self.find(text, counties)
        report = next(a for a in area.areas() if a["county"] == county)
        if not report.get("updated"):
            why = f" ({report['problem']})" if report.get("problem") else ""
            raise CommandError(f"{self.name}: no report for {county} yet{why}; try again in a few minutes")
        line = report_line(county, report, report.get("alerts", []), time.time())
        return CommandResult(console=line, reply=line)

    def find(self, text, counties):
        """The watched county text names: "Taylor, TX", "taylor tx", or just
        "Taylor" when one watched county has that name."""
        try:
            wanted = parse_county(text).lower()
            found = [c for c in counties if c.lower() == wanted]
        except ValueError:
            found = [c for c in counties if county_name(c).lower() == text.strip().lower()]
        if len(found) != 1:
            raise CommandError(f"{self.name}: {text.strip()} isn't a watched county; send {self.name} for the list")
        return found[0]
