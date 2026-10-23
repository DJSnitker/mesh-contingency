import asyncio
import contextlib
import io
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from meshcore import EventType

from mesh_contingency.alerts import (
    ALERTS_FILE,
    KEEP_AFTER_END_SECONDS,
    AlertSettings,
    AlertWatcher,
    hashtag_secret,
    load_alerts,
    parse_county,
)
from mesh_contingency.state import HISTORY_FILE, State
from mesh_contingency.testing import FakeMeshCore, event
from mesh_contingency.weather import alert_counties, county_alerts, county_code


def iso(seconds_from_now):
    """An NWS-style time, seconds from now."""
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() + seconds_from_now))


def alert(id, name="Flood Warning", ends=3600, area="Taylor, TX", same=("048441",), ugc=("TXZ127",)):
    return {"id": id, "event": name, "ends": iso(ends), "expires": iso(ends), "areaDesc": area,
            "geocode": {"SAME": list(same), "UGC": list(ugc)}}


class LoadAlertsTest(unittest.TestCase):
    def test_defaults_turn_it_off(self):
        self.assertEqual(load_alerts({}), AlertSettings((), 10, "#contingency-wx"))

    def test_counties_and_settings(self):
        settings = load_alerts({"alerts": {"counties": ["Taylor, TX", "Jones TX", "taylor county, tx"],
                                           "every_minutes": 15, "channel": "#abilene-wx"}})
        self.assertEqual(settings, AlertSettings(("Taylor, TX", "Jones, TX"), 15, "#abilene-wx"))
        self.assertEqual(load_alerts({"alerts": {"counties": "Palo Pinto, tx"}}).counties, ("Palo Pinto, TX",))

    def test_parse_county(self):
        for text, county in [("Taylor, TX", "Taylor, TX"), ("taylor tx", "taylor, TX"),
                             ("St. Louis County, MO", "St. Louis, MO"), ("Orleans Parish, LA", "Orleans, LA"),
                             ("County, TX", "County, TX")]:
            self.assertEqual(parse_county(text), county)
        for text in ["Taylor", "Taylor, Texas", "Taylor, XX", ", TX", ""]:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "isn't a county and state"):
                parse_county(text)

    def test_channel_defaults_to_the_alert_commands(self):
        config = {"alerts": {"counties": ["Taylor, TX"]}, "commands": {"alert": {"permission": "admin",
                                                                                 "channel": "#local-wx"}}}
        self.assertEqual(load_alerts(config).channel, "#local-wx")

    def test_mistakes_stop_startup(self):
        for section, problem in [
            ({"zipcodes": ["79601"]}, "may only set channel, counties, every_minutes"),
            ({"counties": [441]}, "must be a list of counties"),
            ({"counties": ["Taylor"]}, "isn't a county and state"),
            ({"counties": ["Taylor, TX"], "every_minutes": 2}, "at least 5"),
            ({"counties": ["Taylor, TX"], "every_minutes": True}, "at least 5"),
            ({"counties": ["Taylor, TX"], "channel": "contingency-wx"}, "hashtag channel"),
        ]:
            with self.subTest(section=section), self.assertRaisesRegex(SystemExit, problem):
                load_alerts({"alerts": section})


class WatcherTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.radio = FakeMeshCore()
        # county -> NWS code, or an exception to raise
        self.codes = {"Taylor, TX": "TXC441", "Jones, TX": "TXC253", "Callahan, TX": "TXC059"}
        self.lookups = []  # counties looked up
        self.feed = []  # the active alerts, or an exception to raise
        self.requests = []  # the codes asked for, each request
        self.network = []  # what the network checks before the first round find, then up
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))
        self.enterContext(mock.patch("mesh_contingency.alerts.SEND_GAP", 0))
        self.watcher = self.make_watcher(("Taylor, TX", "Jones, TX"))

    def lookup(self, name, state):
        county = f"{name}, {state}"
        self.lookups.append(county)
        found = self.codes[county]
        if isinstance(found, Exception):
            raise found
        return found

    def fetch(self, codes):
        self.requests.append(codes)
        if isinstance(self.feed, Exception):
            raise self.feed
        return self.feed

    def make_watcher(self, counties, state=None):
        return AlertWatcher(self.radio, AlertSettings(counties, 10, "#contingency-wx"),
                            state or State(self.folder), lookup=self.lookup, fetch=self.fetch,
                            reachable=self.reachable)

    def reachable(self):
        return self.network.pop(0) if self.network else True

    def posted(self):
        return [text for _, text in self.radio.channel_sent]

    async def test_one_request_for_every_county(self):
        await self.watcher.check()
        await self.watcher.check()
        self.assertEqual(self.lookups, ["Taylor, TX", "Jones, TX"])  # only the first round
        self.assertEqual(self.requests, [["TXC441", "TXC253"]] * 2)
        self.assertIn("Auto alerts: Taylor, TX is NWS county TXC441", self.out.getvalue())

    async def test_a_new_alert_is_posted_once(self):
        self.feed = [alert("a1")]
        self.assertEqual(await self.watcher.check(), 1)
        self.assertEqual(len(self.posted()), 1)
        self.assertTrue(self.posted()[0].startswith("Taylor, TX ALERT: Flood Warning | until "), self.posted())
        self.assertEqual(await self.watcher.check(), 0)
        self.assertEqual(len(self.posted()), 1)
        self.assertIn("Auto alerts: posted 1 new alert message(s) for Taylor, TX to #contingency-wx:",
                      self.out.getvalue())

    async def test_an_alert_is_named_by_the_first_county_it_covers(self):
        self.feed = [alert("a1", same=("048253",)), alert("a2", "Wind Advisory", same=("048253", "048441")),
                     alert("a3", "Tornado Warning", same=(), ugc=("TXC253",))]
        await self.watcher.check()
        self.assertEqual([p.split(" | ")[0] for p in self.posted()],
                         ["Jones, TX ALERT: Flood Warning", "Jones, TX ALERT: Tornado Warning",
                          "Taylor, TX ALERT: Wind Advisory"])

    async def test_an_alert_naming_no_watched_county_goes_under_the_first(self):
        self.feed = [alert("a1", same=("048059",), ugc=())]
        await self.watcher.check()
        self.assertTrue(self.posted()[0].startswith("Taylor, TX ALERT:"))

    async def test_keeps_each_countys_alerts_for_the_web_console(self):
        self.assertEqual(self.watcher.current, {})
        self.feed = [alert("a1", "Wind Advisory", same=("048253", "048441")), alert("a2", same=("048059",), ugc=())]
        await self.watcher.check()
        self.assertEqual({county: [a["event"] for a in alerts] for county, alerts in self.watcher.current.items()},
                         {"Taylor, TX": ["Wind Advisory", "Flood Warning"], "Jones, TX": ["Wind Advisory"]})
        first = self.watcher.current["Jones, TX"][0]
        self.assertAlmostEqual(first["ends"], time.time() + 3600, delta=5)
        self.assertEqual(set(first), {"event", "severity", "headline", "ends"})
        # Posted or not, they're what's active now; and none, once they end.
        await self.watcher.check()
        self.assertEqual(len(self.watcher.current["Taylor, TX"]), 2)
        self.feed = []
        await self.watcher.check()
        self.assertEqual(self.watcher.current, {})

    async def test_a_failed_check_keeps_the_alerts_it_had(self):
        self.feed = [alert("a1")]
        await self.watcher.check()
        self.feed = OSError("no network")
        await self.watcher.check()
        self.assertEqual([a["event"] for a in self.watcher.current["Taylor, TX"]], ["Flood Warning"])

    async def test_the_channel_is_added_to_the_radio_if_missing(self):
        self.feed = [alert("a1")]
        await self.watcher.check()
        self.assertEqual(self.radio.channels[1], ("#contingency-wx", hashtag_secret("#contingency-wx")))
        self.assertEqual(self.radio.channel_sent[0][0], 1)

    async def test_nothing_is_looked_up_or_posted_again_after_a_restart(self):
        self.feed = [alert("a1")]
        await self.watcher.check()
        restarted = self.make_watcher(("Taylor, TX", "Jones, TX"), State(self.folder))
        self.feed = [alert("a1"), alert("b1", "Wind Advisory", same=("048253",))]
        await restarted.check()
        self.assertEqual(self.lookups, ["Taylor, TX", "Jones, TX"])
        self.assertEqual(len(self.posted()), 2)
        self.assertTrue(self.posted()[1].startswith("Jones, TX ALERT: Wind Advisory"))

    async def test_counties_no_longer_watched_are_forgotten(self):
        await self.watcher.check()
        restarted = self.make_watcher(("Jones, TX",), State(self.folder))
        self.assertEqual(set(restarted.codes), {"Jones, TX"})

    async def test_several_new_alerts_for_one_county(self):
        self.feed = [alert("a1"), alert("a2", "Wind Advisory")]
        self.assertEqual(await self.watcher.check(), 2)
        self.feed.append(alert("a3", "Tornado Watch"))
        self.assertEqual(await self.watcher.check(), 1)
        self.assertTrue(self.posted()[-1].startswith("Taylor, TX ALERT: Tornado Watch"))

    async def test_alerts_that_have_ended_are_forgotten(self):
        self.feed = [alert("old", ends=-KEEP_AFTER_END_SECONDS - 60), alert("now")]
        await self.watcher.check()
        self.assertEqual(set(self.watcher.posted), {"old", "now"})  # still listed, so kept
        self.feed = [alert("now")]
        await self.watcher.check()
        self.assertEqual(set(self.watcher.posted), {"now"})
        self.assertEqual(set(State(self.folder).store(ALERTS_FILE).data["posted"]), {"now"})

    async def test_an_alert_without_an_id(self):
        self.feed = [{k: v for k, v in alert("x").items() if k != "id"}]
        await self.watcher.check()
        await self.watcher.check()
        self.assertEqual(len(self.posted()), 1)

    async def test_a_county_that_cant_be_looked_up_is_retried_by_itself(self):
        self.codes["Jones, TX"] = OSError("timed out")
        self.feed = [alert("a1")]
        await self.watcher.check()
        await self.watcher.check()
        self.assertEqual(self.out.getvalue().count("Auto alerts: couldn't look up the NWS code of Jones, TX "
                                                   "(timed out); trying again every 10 min"), 1)
        self.assertEqual(self.watcher.unmapped, {"Jones, TX": "timed out"})
        self.assertEqual(self.requests, [["TXC441"]] * 2)  # the other county is still checked
        self.assertEqual(len(self.posted()), 1)
        self.codes["Jones, TX"] = "TXC253"
        await self.watcher.check()
        self.assertEqual(self.lookups, ["Taylor, TX", "Jones, TX", "Jones, TX", "Jones, TX"])
        self.assertEqual(self.watcher.unmapped, {})
        self.assertEqual(self.requests[-1], ["TXC441", "TXC253"])

    async def test_nothing_looked_up_means_no_request(self):
        self.codes["Taylor, TX"] = self.codes["Jones, TX"] = OSError("no network")
        self.assertEqual(await self.watcher.check(), 0)
        self.assertEqual(self.requests, [])
        self.assertIsNone(self.watcher.last_check)

    async def test_a_failed_request_is_logged_once_and_retried(self):
        self.feed = OSError("timed out")
        await self.watcher.check()
        await self.watcher.check()
        self.assertEqual(self.out.getvalue().count("Auto alerts: couldn't check for alerts (timed out); trying again "
                                                   "every 10 min"), 1)
        self.assertEqual(self.watcher.problem, "timed out")
        self.assertIsNone(self.watcher.last_check)
        self.feed = [alert("a1")]
        await self.watcher.check()
        self.assertIn("Auto alerts: checking for alerts again", self.out.getvalue())
        self.assertIsNone(self.watcher.problem)
        self.assertIsNotNone(self.watcher.last_check)
        self.assertEqual(len(self.posted()), 1)

    async def test_map_counties_again(self):
        await self.watcher.check()
        self.codes["Jones, TX"] = "TXC999"
        results = await self.watcher.map_counties(["Jones, TX"])
        self.assertEqual(results, [("Jones, TX", "TXC999", None)])
        self.assertEqual(State(self.folder).store(ALERTS_FILE).data["counties"]["Jones, TX"]["code"], "TXC999")
        await self.watcher.check()
        self.assertEqual(self.requests[-1], ["TXC441", "TXC999"])

    async def test_zones_from_the_zipcode_version_are_dropped(self):
        store = State(self.folder).store(ALERTS_FILE)
        store.data["zones"] = {"79601": {"place": "Abilene, TX", "zones": ["TXC441"]}}
        store.save()
        watcher = self.make_watcher(("Taylor, TX",), State(self.folder))
        self.assertNotIn("zones", watcher.store.data)

    async def test_alerts_that_couldnt_be_posted_are_tried_again(self):
        self.feed = [alert("a1")]
        self.radio.channel_result = event(EventType.ERROR, {"reason": "busy"})
        with self.assertRaisesRegex(RuntimeError, "radio rejected channel message 1 of 1"):
            await self.watcher.check()
        self.assertEqual(self.watcher.posted, {})
        self.radio.channel_result = event(EventType.OK)
        self.assertEqual(await self.watcher.check(), 1)

    async def test_no_free_channel_slot(self):
        self.radio.channels = [(f"ch{i}", bytes([i + 1]) * 16) for i in range(8)]
        self.feed = [alert("a1")]
        with self.assertRaisesRegex(Exception, "no free channel slot on the radio for #contingency-wx"):
            await self.watcher.check()
        self.assertEqual(self.watcher.posted, {})

    async def test_posts_are_in_the_history(self):
        self.feed = [alert("a1")]
        await self.watcher.check()
        entries = State(self.folder).store(HISTORY_FILE).data["entries"]
        self.assertEqual([(e["by"], e["what"]) for e in entries],
                         [("auto", "posted 1 new Taylor, TX alert message(s) to #contingency-wx")])

    async def test_a_failed_round_doesnt_stop_the_watcher(self):
        self.feed = [alert("a1")]
        self.radio.channel_result = event(EventType.ERROR, {"reason": "busy"})
        sleeps = []

        async def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                raise asyncio.CancelledError
            self.radio.channel_result = event(EventType.OK)

        with mock.patch("mesh_contingency.alerts.asyncio.sleep", sleep), self.assertRaises(asyncio.CancelledError):
            await self.watcher.run()
        self.assertEqual(sleeps, [600, 600])
        self.assertIn("Auto alerts: radio rejected channel message 1 of 1", self.out.getvalue())
        self.assertEqual(len(self.posted()), 2)  # refused, then sent on the second round
        self.assertEqual(set(self.watcher.posted), {"a1"})
        self.assertEqual(self.watcher.state.counts["errors"], 1)

    async def test_the_first_round_waits_for_the_network(self):
        self.network = [False, False]
        sleeps = []

        async def sleep(seconds):
            sleeps.append(seconds)

        with mock.patch("mesh_contingency.alerts.asyncio.sleep", sleep):
            self.assertTrue(await self.watcher.wait_for_network())
        self.assertEqual(sleeps, [5, 5])
        self.assertEqual(self.out.getvalue(), "Auto alerts: no network yet; waiting up to 2 min before the "
                                              "first check\nAuto alerts: network up after 10s\n")

    async def test_no_wait_when_the_network_is_up(self):
        with mock.patch("mesh_contingency.alerts.asyncio.sleep") as sleep:
            self.assertTrue(await self.watcher.wait_for_network())
        sleep.assert_not_called()
        self.assertEqual(self.out.getvalue(), "")

    async def test_no_network_at_all_checks_anyway(self):
        self.network = [False] * 100
        sleeps = []

        async def sleep(seconds):
            sleeps.append(seconds)

        with mock.patch("mesh_contingency.alerts.asyncio.sleep", sleep):
            self.assertFalse(await self.watcher.wait_for_network())
        self.assertEqual(sum(sleeps), 120)
        self.assertIn("Auto alerts: still no network after 2 min; checking anyway", self.out.getvalue())


class WeatherCountiesTest(unittest.TestCase):
    def test_county_code(self):
        found = {"features": [{"properties": {"id": "TXC253", "name": "Jones"}},
                              {"properties": {"id": "TXC441", "name": "Taylor"}}]}
        with mock.patch("mesh_contingency.weather._get_json", return_value=found) as get:
            self.assertEqual(county_code("taylor", "TX"), "TXC441")
            with self.assertRaisesRegex(ValueError, "the NWS has no county 'Tailor' in TX"):
                county_code("Tailor", "TX")
        get.assert_called_with("https://api.weather.gov/zones?type=county&area=TX")

    def test_county_alerts_is_one_request(self):
        found = {"features": [{"properties": {"id": "x"}}]}
        with mock.patch("mesh_contingency.weather._get_json", return_value=found) as get:
            self.assertEqual(county_alerts(["TXC441", "TXC253"]), [{"id": "x"}])
        get.assert_called_once_with("https://api.weather.gov/alerts/active?zone=TXC441,TXC253")

    def test_alert_counties(self):
        self.assertEqual(alert_counties({"geocode": {"UGC": ["TXZ127", "TXC059"], "SAME": ["048441", "012086"]}}),
                         {"TXC059", "TXC441", "FLC086"})
        self.assertEqual(alert_counties({"geocode": {"SAME": ["099999", "48"]}}), set())
        self.assertEqual(alert_counties({}), set())


if __name__ == "__main__":
    unittest.main()
