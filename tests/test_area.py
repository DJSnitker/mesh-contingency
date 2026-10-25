"""area: the weather now in the watched counties, from the bot's reports."""

import time
import unittest
from types import SimpleNamespace
from unittest import mock

from mesh_contingency.api import MAX_REPLY_LEN, CommandError, Sender
from mesh_contingency.area_weather import AreaWeather
from mesh_contingency.commands.area import AreaCommand, report_line
from mesh_contingency.state import State
from mesh_contingency.testing import make_context

SENDER = Sender("Dana", "d0" * 32)
TAYLOR, JONES, HARRIS = "Taylor, TX", "Jones, TX", "Harris, TX"


def conditions(text="Clear", temp=63.0, feels=None, gust=None, observed=None):
    return {"station": "Abilene Regional Airport", "observed": observed, "text": text, "temp_f": temp,
            "feels_f": feels, "humidity": 62.0, "wind_mph": 7.0, "gust_mph": gust, "wind_dir": "SE",
            "periods": [{"name": "Tonight", "temp": 55, "unit": "F", "text": "Mostly Clear", "pop": 20,
                         "wind": "S 5 mph"}]}


class AreaCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = State()
        self.watcher = SimpleNamespace(
            settings=SimpleNamespace(counties=[TAYLOR, JONES, HARRIS]),
            codes={TAYLOR: {"code": "TXC441"}, JONES: {"code": "TXC253"}, HARRIS: {"code": "TXC201"}},
            current={JONES: [{"event": "Wind Advisory"}, {"event": "Wind Advisory"}]})
        self.answers = {"TXC441": conditions(), "TXC253": conditions("Windy", 70.0, gust=35.0)}
        self.state.alert_watcher = self.watcher
        self.state.area_weather = AreaWeather(self.watcher, self.state, point=lambda code: {
            "code": code, "place": code, "stations": [], "forecast": ""}, conditions=self.conditions)
        self.command = AreaCommand(make_context("area", state=self.state))

    def conditions(self, point, periods):
        found = self.answers.get(point["code"])
        if found is None:
            raise OSError("network down")
        return found

    async def refresh(self):
        with mock.patch("mesh_contingency.area_weather.GAP", 0):
            await self.state.area_weather.refresh()

    async def test_lists_the_counties(self):
        result = await self.command.execute("", SENDER)
        self.assertEqual(result.reply, ["area: Taylor, TX; Jones, TX; Harris, TX"])

    async def test_a_county_report(self):
        await self.refresh()
        result = await self.command.execute("taylor tx", SENDER)
        self.assertEqual(result.reply, "Taylor, TX 63F, Clear | SE7mph | just now | Tonight: 55F Mostly Clear 20%")
        # By name alone, when one watched county has it; alerts first, once each.
        result = await self.command.execute("Jones", SENDER)
        self.assertEqual(result.reply, "Jones, TX ALERT: Wind Advisory | 70F, Windy | SE7mph G35 | just now | "
                                       "Tonight: 55F Mostly Clear 20%")

    async def test_the_report_says_how_old_it_is(self):
        await self.refresh()
        report = self.state.area_weather.reports[TAYLOR]
        report["updated"] = report["observed"] = time.time() - 3 * 3600
        report["problem"] = "network down"
        result = await self.command.execute(TAYLOR, SENDER)
        self.assertIn("| 3h ago |", result.reply)

    async def test_no_report_yet(self):
        await self.refresh()
        with self.assertRaisesRegex(CommandError, r"area: no report for Harris, TX yet \(network down\)"):
            await self.command.execute("Harris, TX", SENDER)

    async def test_not_a_watched_county(self):
        for text in ("Dallas, TX", "Dallas", "Taylor, OK"):
            with self.assertRaisesRegex(CommandError, "isn't a watched county; send area for the list"):
                await self.command.execute(text, SENDER)

    async def test_needs_counties(self):
        self.assertTrue(self.command.enabled)
        self.watcher.settings.counties = []
        self.assertFalse(self.command.enabled)
        self.state.alert_watcher = None
        self.assertFalse(self.command.enabled)
        self.state.area_weather = None
        with self.assertRaisesRegex(CommandError, "no counties are watched"):
            await self.command.execute("", SENDER)

    def test_feels_like_only_when_it_differs(self):
        now = time.time()
        line = report_line(TAYLOR, {**conditions(temp=95.0, feels=104.0), "updated": now}, [], now)
        self.assertIn("95F, Clear, feels 104F", line)
        line = report_line(TAYLOR, {**conditions(temp=95.0, feels=96.0), "updated": now}, [], now)
        self.assertNotIn("feels", line)

    def test_a_long_report_fits_one_message(self):
        now = time.time()
        alerts = [{"event": f"Very Long Warning Name {i}"} for i in range(6)]
        line = report_line(TAYLOR, {**conditions(), "updated": now}, alerts, now)
        self.assertLessEqual(len(line), MAX_REPLY_LEN)
        self.assertTrue(line.startswith("Taylor, TX ALERT: Very Long Warning Name 0"))


if __name__ == "__main__":
    unittest.main()
