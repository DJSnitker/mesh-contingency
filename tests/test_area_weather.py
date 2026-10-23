"""The weather now in each watched county, for the web console."""

import contextlib
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from mesh_contingency.area_weather import AREA_FILE, EVERY_MINUTES, RETRY_SECONDS, AreaWeather
from mesh_contingency.state import State
from mesh_contingency.weather import area_conditions, compass, county_point

TAYLOR, JONES = "Taylor, TX", "Jones, TX"


def point(code):
    return {"lat": 32.3, "lon": -99.9, "place": f"Town of {code}", "forecast": f"https://nws/{code}/forecast",
            "stations": [["KABI", "Abilene Regional Airport"]]}


def conditions(text="Clear", temp=63.0):
    return {"station": "Abilene Regional Airport", "observed": "2026-10-23T13:52:00+00:00", "text": text,
            "temp_f": temp, "feels_f": None, "humidity": 62.0, "wind_mph": 7.0, "gust_mph": None, "wind_dir": "SE",
            "periods": [{"name": "Today", "temp": 85, "unit": "F", "text": "Mostly Sunny", "pop": 0,
                         "wind": "SSE 10 to 15 mph"}]}


class AreaWeatherTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.state = State(self.folder)
        self.watcher = SimpleNamespace(settings=SimpleNamespace(counties=[TAYLOR, JONES]),
                                       codes={TAYLOR: {"code": "TXC441"}, JONES: {"code": "TXC253"}},
                                       current={JONES: [{"event": "Wind Advisory", "severity": "Minor",
                                                         "headline": None, "ends": None}]})
        self.points = []  # codes looked up
        self.asked = []  # the points asked about
        self.answers = {}  # code -> the conditions, or an exception to raise
        self.enterContext(mock.patch("mesh_contingency.area_weather.GAP", 0))
        self.area = self.make()

    def make(self):
        return AreaWeather(self.watcher, self.state, point=self.point, conditions=self.conditions)

    def point(self, code):
        self.points.append(code)
        return point(code)

    def conditions(self, at, periods):
        self.asked.append((at["code"], periods))
        found = self.answers.get(at["code"], conditions())
        if isinstance(found, Exception):
            raise found
        return found

    async def test_each_county_in_order_with_its_alerts(self):
        self.assertEqual(await self.area.refresh(), 2)
        areas = self.area.areas()
        self.assertEqual([a["county"] for a in areas], [TAYLOR, JONES])
        taylor = areas[0]
        self.assertEqual((taylor["place"], taylor["text"], taylor["temp_f"]), ("Town of TXC441", "Clear", 63.0))
        self.assertEqual(taylor["observed"], 1792763520.0)  # 2026-10-23 13:52 UTC, as time.time()
        self.assertAlmostEqual(taylor["updated"], time.time(), delta=5)
        self.assertIsNone(taylor["problem"])
        self.assertEqual(taylor["alerts"], [])
        self.assertEqual([a["event"] for a in areas[1]["alerts"]], ["Wind Advisory"])
        self.assertEqual(self.asked, [("TXC441", 3), ("TXC253", 3)])

    async def test_where_to_ask_is_looked_up_once_and_kept(self):
        await self.area.refresh()
        await self.area.refresh()
        self.assertEqual(self.points, ["TXC441", "TXC253"])
        # After a restart too: it's in AREA_FILE.
        self.state = State(self.folder)
        self.area = self.make()
        await self.area.refresh()
        self.assertEqual(self.points, ["TXC441", "TXC253"])
        self.assertEqual(self.state.store(AREA_FILE).data["points"][TAYLOR]["code"], "TXC441")

    async def test_a_failure_keeps_the_last_report_and_says_why(self):
        await self.area.refresh()
        self.answers["TXC441"] = OSError("no network")
        self.assertEqual(await self.area.refresh(), 1)
        taylor = self.area.areas()[0]
        self.assertEqual((taylor["text"], taylor["problem"]), ("Clear", "no network"))
        self.answers["TXC441"] = conditions("Rain", 55.0)
        await self.area.refresh()
        taylor = self.area.areas()[0]
        self.assertEqual((taylor["text"], taylor["problem"]), ("Rain", None))

    async def test_never_fetched_says_why(self):
        self.answers["TXC441"] = TimeoutError()
        await self.area.refresh()
        taylor = self.area.areas()[0]
        self.assertEqual(taylor, {"county": TAYLOR, "alerts": [], "problem": "TimeoutError"})

    async def test_a_county_not_looked_up_yet(self):
        del self.watcher.codes[JONES]
        self.assertEqual(await self.area.refresh(), 1)
        self.assertEqual(self.area.areas()[1]["problem"], "the alert watcher hasn't looked it up yet")

    async def test_a_county_that_changed_code_or_left_is_looked_up_again_or_dropped(self):
        await self.area.refresh()
        self.watcher.codes[TAYLOR] = {"code": "TXC999"}
        self.watcher.settings.counties = [TAYLOR]
        await self.area.refresh()
        self.assertEqual(self.points, ["TXC441", "TXC253", "TXC999"])
        self.assertEqual(list(self.state.store(AREA_FILE).data["points"]), [TAYLOR])
        self.assertEqual([a["county"] for a in self.area.areas()], [TAYLOR])

    async def test_runs_every_15_min_and_sooner_after_getting_nothing(self):
        self.answers = {"TXC441": OSError("down"), "TXC253": OSError("down")}
        sleeps = []

        async def sleep(seconds):
            if seconds == 0:  # GAP, between counties
                return
            sleeps.append(seconds)
            if len(sleeps) == 2:
                raise StopAsyncIteration
            self.answers.clear()

        with mock.patch("asyncio.sleep", sleep), contextlib.suppress(StopAsyncIteration):
            await self.area.run()
        self.assertEqual(sleeps, [RETRY_SECONDS, EVERY_MINUTES * 60])

    def test_describe(self):
        self.assertEqual(self.area.describe(), "2 counties every 15 min")


class NwsTest(unittest.TestCase):
    """county_point and area_conditions, with the NWS's answers faked."""

    def answers(self, pages):
        def get(url):
            found = pages[url]
            if isinstance(found, Exception):
                raise found
            return found

        return mock.patch("mesh_contingency.weather._get_json", get)

    def test_county_point_is_the_middle_of_its_outline(self):
        square = [[-100.0, 32.0], [-99.0, 32.0], [-99.0, 33.0], [-100.0, 33.0]]
        pages = {
            "https://api.weather.gov/zones/county/TXC441": {"geometry": {"type": "Polygon", "coordinates": [square]}},
            "https://api.weather.gov/points/32.5000,-99.5000": {"properties": {
                "relativeLocation": {"properties": {"city": "Buffalo Gap", "state": "TX"}},
                "forecast": "https://nws/forecast", "observationStations": "https://nws/stations"}},
            "https://nws/stations": {"features": [
                {"properties": {"stationIdentifier": f"K{n}", "name": f"Station {n}"}} for n in range(5)]},
        }
        with self.answers(pages):
            found = county_point("TXC441")
        self.assertEqual(found, {"lat": 32.5, "lon": -99.5, "place": "Buffalo Gap, TX",
                                 "forecast": "https://nws/forecast",
                                 "stations": [["K0", "Station 0"], ["K1", "Station 1"], ["K2", "Station 2"]]})

    def test_conditions_from_the_first_station_with_a_temperature(self):
        import urllib.error

        here = {"place": "Buffalo Gap, TX", "forecast": "https://nws/forecast",
                "stations": [["KAAA", "Down"], ["KBBB", "No temperature"], ["KABI", "Abilene"]]}
        latest = "https://api.weather.gov/stations/{}/observations/latest"
        pages = {
            latest.format("KAAA"): urllib.error.HTTPError("u", 500, "down", {}, None),
            latest.format("KBBB"): {"properties": {"temperature": {"value": None}}},
            latest.format("KABI"): {"properties": {
                "timestamp": "2026-10-23T13:52:00+00:00", "textDescription": "Clear",
                "temperature": {"value": 20.0}, "windChill": {"value": None}, "heatIndex": {"value": None},
                "relativeHumidity": {"value": 62.5}, "windSpeed": {"value": 16.09344},
                "windGust": {"value": None}, "windDirection": {"value": 160}}},
            "https://nws/forecast": {"properties": {"periods": [
                {"name": n, "temperature": t, "temperatureUnit": "F", "shortForecast": f, "windSpeed": "10 mph",
                 "windDirection": "SSE", "probabilityOfPrecipitation": {"value": p}}
                for n, t, f, p in [("Today", 85, "Mostly Sunny", 0), ("Tonight", 60, "Partly Cloudy", None),
                                   ("Saturday", 82, "Showers", 40), ("Saturday Night", 58, "Clear", 10)]]}},
        }
        with self.answers(pages):
            found = area_conditions(here, 3)
        self.assertEqual(found["station"], "Abilene")
        self.assertEqual(found["text"], "Clear")
        self.assertAlmostEqual(found["temp_f"], 68.0)
        self.assertAlmostEqual(found["wind_mph"], 10.0, places=3)
        self.assertEqual((found["wind_dir"], found["gust_mph"], found["feels_f"]), ("SSE", None, None))
        self.assertEqual([(p["name"], p["temp"], p["text"], p["pop"], p["wind"]) for p in found["periods"]],
                         [("Today", 85, "Mostly Sunny", 0, "SSE 10 mph"), ("Tonight", 60, "Partly Cloudy", None,
                                                                         "SSE 10 mph"),
                          ("Saturday", 82, "Showers", 40, "SSE 10 mph")])

    def test_no_station_reporting(self):
        here = {"place": "X", "forecast": "https://nws/forecast", "stations": []}
        with self.answers({"https://nws/forecast": {"properties": {"periods": []}}}):
            found = area_conditions(here, 3)
        self.assertEqual((found["station"], found["observed"], found["temp_f"], found["periods"]),
                         (None, None, None, []))

    def test_compass(self):
        self.assertEqual([compass(d) for d in (None, 0, 160, 180, 350)], ["", "N", "SSE", "S", "N"])


if __name__ == "__main__":
    unittest.main()
