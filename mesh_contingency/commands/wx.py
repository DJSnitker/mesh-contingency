"""wx <zipcode>: current conditions, precipitation and alerts."""

import asyncio

from ..weather import POP_HOURS, c_to_f, fetch_weather, kmh_to_mph, mm_to_in, value

from ..api import Command, CommandError, CommandResult


def _compass(deg):
    if deg is None:
        return ""
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[round(deg / 45) % 8]


def _fmt(val, unit, digits=0):
    return "n/a" if val is None else f"{val:.{digits}f}{unit}"


def format_report(wx):
    """Return the full multi-line report for the console."""
    obs = wx["obs"]
    lines = [f"Weather for {wx['zipcode']} ({wx['place']})"]
    if obs is None:
        lines.append("  No current observations available.")
    else:
        temp_c = value(obs, "temperature")
        feels_c = value(obs, "heatIndex") or value(obs, "windChill")
        wind = kmh_to_mph(value(obs, "windSpeed"))
        gust = kmh_to_mph(value(obs, "windGust"))
        wind_str = f"{_compass(value(obs, 'windDirection'))} {_fmt(wind, ' mph')}".strip()
        if gust:
            wind_str += f", gusts {_fmt(gust, ' mph')}"
        lines += [
            f"  Station:    {wx['station']} (as of {obs.get('timestamp', 'unknown')})",
            f"  Conditions: {obs.get('textDescription') or 'n/a'}",
            f"  Temp:       {_fmt(c_to_f(temp_c), 'F')} ({_fmt(temp_c, 'C')})",
        ]
        if feels_c is not None:
            lines.append(f"  Feels like: {_fmt(c_to_f(feels_c), 'F')}")
        lines += [
            f"  Humidity:   {_fmt(value(obs, 'relativeHumidity'), '%')}",
            f"  Wind:       {wind_str}",
            f"  Dewpoint:   {_fmt(c_to_f(value(obs, 'dewpoint')), 'F')}",
        ]
        rain = mm_to_in(value(obs, "precipitationLastHour"))
        if rain:
            lines.append(f"  Precip:     {rain:.2f} in last hour")
    if wx["pop"] is not None:
        lines.append(f"  Precip chance (next {POP_HOURS}h): {wx['pop']:.0f}%")

    alerts = wx["alerts"]
    if not alerts:
        lines.append("  Alerts:     none")
    else:
        lines.append(f"  Alerts ({len(alerts)}):")
        for a in alerts:
            lines.append(f"    - {a.get('event')} [{a.get('severity')}]")
            lines.append(f"      {a.get('onset') or a.get('effective')} -> {a.get('ends') or a.get('expires')}")
            if a.get("headline"):
                lines.append(f"      {a['headline']}")
    return "\n".join(lines)


def format_short(wx):
    """Return a one-line mesh reply: alerts, then precipitation, then temperature and wind."""
    obs = wx["obs"]
    sections = []

    # Dedupe alert names: NWS often issues the same event for several zones.
    events = list(dict.fromkeys(a.get("event") for a in wx["alerts"] if a.get("event")))
    if events:
        sections.append("ALERT: " + "; ".join(events))

    precip = []
    if obs is not None and obs.get("textDescription"):
        precip.append(obs["textDescription"])
    rain = mm_to_in(value(obs, "precipitationLastHour"))
    if rain:
        precip.append(f"{rain:.2f}in/hr")
    if wx["pop"] is not None:
        precip.append(f"{wx['pop']:.0f}% precip {POP_HOURS}h")
    if precip:
        sections.append(", ".join(precip))

    if obs is not None:
        temp = [_fmt(c_to_f(value(obs, "temperature")), "F")]
        wind = kmh_to_mph(value(obs, "windSpeed"))
        if wind is not None:
            temp.append(f"{_compass(value(obs, 'windDirection'))}{wind:.0f}mph")
        gust = kmh_to_mph(value(obs, "windGust"))
        if gust:
            temp.append(f"G{gust:.0f}")
        sections.append(" ".join(temp))
    else:
        sections.append("no current obs")

    return Command.fit_reply(wx["zipcode"], sections)


class WxCommand(Command):
    args = "<zipcode>"
    summary = "Weather, precipitation and alerts for a US zipcode"

    async def execute(self, text, sender):
        args = text.split()
        if len(args) != 1:
            raise CommandError(f"usage: {self.usage}")
        try:
            wx = await asyncio.to_thread(fetch_weather, args[0])
        except ValueError as e:
            raise CommandError(f"{self.name}: {e}") from e
        return CommandResult(console=format_report(wx), reply=format_short(wx))
