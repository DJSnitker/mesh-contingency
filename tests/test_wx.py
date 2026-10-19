import unittest
from unittest import mock

from commands.base import MAX_REPLY_LEN, PUBLIC, CommandError, Sender
from commands.wx import WxCommand, _compass, _fmt, format_report, format_short

SENDER = Sender("Dana", "d0d0d0d0d0d0")


def obs(**fields):
    """Observation properties with NWS-style {"value": ...} fields."""
    out = {"textDescription": fields.pop("text", None), "timestamp": "2026-10-19T12:00:00+00:00"}
    out.update({k: {"value": v} for k, v in fields.items()})
    return out


def wx(observation=None, pop=None, alerts=(), zipcode="12345"):
    return {"zipcode": zipcode, "place": "Town, ST", "station": "Town Airport",
            "obs": observation, "pop": pop, "alerts": list(alerts)}


STORMY = obs(text="Heavy Rain", temperature=20, windSpeed=40, windDirection=200,
             windGust=70, precipitationLastHour=8, relativeHumidity=90, dewpoint=18)


class HelpersTest(unittest.TestCase):
    def test_compass(self):
        self.assertEqual(_compass(0), "N")
        self.assertEqual(_compass(90), "E")
        self.assertEqual(_compass(200), "S")
        self.assertEqual(_compass(350), "N")
        self.assertEqual(_compass(None), "")

    def test_fmt(self):
        self.assertEqual(_fmt(61.6, "F"), "62F")
        self.assertEqual(_fmt(1.234, "in", 2), "1.23in")
        self.assertEqual(_fmt(None, "F"), "n/a")


class FormatShortTest(unittest.TestCase):
    def test_temperature_and_wind(self):
        reply = format_short(wx(STORMY, pop=90))
        self.assertEqual(reply, "12345 Heavy Rain, 0.31in/hr, 90% precip 6h | 68F S25mph G43")

    def test_alerts_come_first_and_are_deduplicated(self):
        alerts = [{"event": "Flood Warning"}, {"event": "Flood Warning"}, {"event": "Wind Advisory"}, {}]
        reply = format_short(wx(STORMY, pop=90, alerts=alerts))
        self.assertTrue(reply.startswith("12345 ALERT: Flood Warning; Wind Advisory | Heavy Rain"))

    def test_lower_priority_sections_dropped_when_full(self):
        alerts = [{"event": e} for e in ("Flood Warning", "Severe Thunderstorm Warning", "Wind Advisory")]
        stormier = dict(STORMY, textDescription="Heavy Rain and Fog/Mist")
        reply = format_short(wx(stormier, pop=90, alerts=alerts))
        self.assertIn("Heavy Rain and Fog/Mist", reply)
        self.assertNotIn("68F", reply)
        self.assertLessEqual(len(reply), MAX_REPLY_LEN)

    def test_many_alerts_never_exceed_limit(self):
        alerts = [{"event": f"Very Long Hazard Statement Number {i}"} for i in range(10)]
        reply = format_short(wx(STORMY, pop=90, alerts=alerts))
        self.assertEqual(len(reply), MAX_REPLY_LEN)
        self.assertTrue(reply.endswith("..."))

    def test_no_wind_and_no_gust(self):
        reply = format_short(wx(obs(text="Clear", temperature=15), pop=0))
        self.assertEqual(reply, "12345 Clear, 0% precip 6h | 59F")

    def test_no_observation(self):
        self.assertEqual(format_short(wx(None)), "12345 no current obs")

    def test_reply_is_ascii(self):
        format_short(wx(STORMY, pop=90)).encode("ascii")


class FormatReportTest(unittest.TestCase):
    def test_full_report(self):
        report = format_report(wx(STORMY, pop=90, alerts=[{
            "event": "Flood Warning", "severity": "Severe", "onset": "start", "ends": "end",
            "headline": "Flood Warning until tonight"}]))
        for expected in ("Weather for 12345 (Town, ST)", "Station:    Town Airport",
                         "Conditions: Heavy Rain", "Temp:       68F (20C)", "Humidity:   90%",
                         "Wind:       S 25 mph, gusts 43 mph", "Dewpoint:   64F",
                         "Precip:     0.31 in last hour", "Precip chance (next 6h): 90%",
                         "Alerts (1):", "- Flood Warning [Severe]", "start -> end",
                         "Flood Warning until tonight"):
            self.assertIn(expected, report)

    def test_feels_like_uses_heat_index_or_wind_chill(self):
        self.assertIn("Feels like: 95F", format_report(wx(obs(temperature=30, heatIndex=35))))
        self.assertIn("Feels like: 14F", format_report(wx(obs(temperature=-5, windChill=-10))))
        self.assertNotIn("Feels like", format_report(wx(obs(temperature=10))))

    def test_alert_falls_back_to_effective_and_expires(self):
        report = format_report(wx(obs(temperature=10), alerts=[
            {"event": "Heat Advisory", "severity": "Minor", "effective": "eff", "expires": "exp"}]))
        self.assertIn("eff -> exp", report)

    def test_missing_data(self):
        report = format_report(wx(None))
        self.assertIn("No current observations available.", report)
        self.assertIn("Alerts:     none", report)
        self.assertNotIn("Precip chance", report)


class WxCommandTest(unittest.IsolatedAsyncioTestCase):
    def test_is_public(self):
        self.assertEqual(WxCommand.name, "wx")
        self.assertEqual(WxCommand.permission, PUBLIC)

    async def test_usage_errors(self):
        for text in ("", "12345 67890"):
            with self.assertRaisesRegex(CommandError, "usage: wx <zipcode>"):
                await WxCommand().execute(text, SENDER)

    async def test_invalid_zip_becomes_command_error(self):
        with mock.patch("commands.wx.fetch_weather", side_effect=ValueError("unknown zipcode 00000")):
            with self.assertRaisesRegex(CommandError, "^wx: unknown zipcode 00000$"):
                await WxCommand().execute("00000", SENDER)

    async def test_other_errors_propagate(self):
        with mock.patch("commands.wx.fetch_weather", side_effect=OSError("network down")):
            with self.assertRaises(OSError):
                await WxCommand().execute("12345", SENDER)

    async def test_success(self):
        data = wx(STORMY, pop=90)
        with mock.patch("commands.wx.fetch_weather", return_value=data) as fetch:
            result = await WxCommand().execute("12345", SENDER)
        fetch.assert_called_once_with("12345")
        self.assertEqual(result.reply, format_short(data))
        self.assertEqual(result.console, format_report(data))


if __name__ == "__main__":
    unittest.main()
