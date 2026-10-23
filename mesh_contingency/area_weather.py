"""The weather now in each county [alerts] watches, for the web console's
dashboard: the latest reading from the nearest station and the next periods
of the forecast, whether or not there's an alert.

The bot asks the NWS every EVERY_MINUTES and keeps the last report, so
opening the dashboard never calls api.weather.gov, and when the internet is
down the page still shows the last one, with its time and why it's old.
Where to ask about each county (its middle, the nearest stations, its
forecast's address) is looked up once and kept in AREA_FILE. The counties'
NWS codes are the alert watcher's.
"""

import asyncio
import datetime
import time

from .weather import area_conditions, county_point

AREA_FILE = "area_weather.json"
EVERY_MINUTES = 15
# After a round that got nothing at all (no network yet, at boot), the next
# one comes sooner (seconds).
RETRY_SECONDS = 60
# Forecast periods per county, e.g. Today, Tonight, Saturday.
PERIODS = 3
# Between counties, to go easy on the NWS (seconds).
GAP = 0.5


def _timestamp(iso):
    try:
        return datetime.datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return None


class AreaWeather:
    def __init__(self, watcher, state, point=None, conditions=None):
        self.watcher = watcher
        self.point = point or county_point  # NWS county code -> where to ask
        self.conditions = conditions or area_conditions  # (point, periods) -> the weather now
        self.store = state.store(AREA_FILE)
        self.reports = {}  # county -> its last report, and why the last try failed

    @property
    def counties(self):
        return self.watcher.settings.counties

    def describe(self):
        """For startup."""
        return f"{len(self.counties)} count{'y' if len(self.counties) == 1 else 'ies'} every {EVERY_MINUTES} min"

    async def refresh(self):
        """One round, county by county. Returns how many got a report."""
        points = self.store.data.setdefault("points", {})
        for county in [c for c in points if c not in self.counties]:
            del points[county]  # no longer watched
        got = 0
        for county in self.counties:
            report = self.reports.setdefault(county, {})
            code = self.watcher.codes.get(county, {}).get("code")
            if code is None:
                report["problem"] = "the alert watcher hasn't looked it up yet"
                continue
            try:
                point = points.get(county)
                if point is None or point.get("code") != code:
                    point = points[county] = {"code": code, **await asyncio.to_thread(self.point, code)}
                    self.store.save()
                found = await asyncio.to_thread(self.conditions, point, PERIODS)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # the network or the NWS
                report["problem"] = str(e) or type(e).__name__
                continue
            report.clear()
            report.update(found, observed=_timestamp(found["observed"]), place=point["place"], updated=time.time(),
                          problem=None)
            got += 1
            await asyncio.sleep(GAP)
        return got

    async def run(self):
        """Refresh every EVERY_MINUTES until cancelled; a round that fails is
        tried again, never stopping the bot."""
        while True:
            try:
                got = await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"Area weather: {e}; trying again in {EVERY_MINUTES} min", flush=True)
                got = 1
            await asyncio.sleep(EVERY_MINUTES * 60 if got or not self.counties else RETRY_SECONDS)

    def areas(self):
        """For /api/weather: each county in [alerts] order, with its report
        and the alerts the watcher found for it."""
        return [{"county": county, "alerts": self.watcher.current.get(county, []), **self.reports.get(county, {})}
                for county in self.counties]
