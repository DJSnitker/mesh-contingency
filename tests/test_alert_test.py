import asyncio
import contextlib
import datetime
import io
import tempfile
import time
import unittest
import zoneinfo
from pathlib import Path
from unittest import mock

from meshcore import EventType

from mesh_contingency.alerts import (
    ALERTS_FILE,
    AlertTest,
    TestSettings,
    load_alert_test,
    next_weekly,
    parse_weekly,
    when_text,
)
from mesh_contingency.api import MAX_REPLY_LEN, CommandError, Sender
from mesh_contingency.commands.testalert import TestAlertCommand
from mesh_contingency.state import HISTORY_FILE, State
from mesh_contingency.testing import FakeMeshCore, event, make_context

CHICAGO = zoneinfo.ZoneInfo("America/Chicago")
ADMIN = Sender("Admin", "ad" * 32)
WED_5PM = (2, 17, 0)


def chicago(*args):
    return datetime.datetime(*args, tzinfo=CHICAGO).timestamp()


class ParseWeeklyTest(unittest.TestCase):
    def test_days_and_times(self):
        for text in ["Wednesday 17:00", "wed 5:00pm", "Wed 5PM", "WED 5:00 PM", "wednes 17:00", "Wed 5 p.m."]:
            self.assertEqual(parse_weekly(text), WED_5PM, text)
        self.assertEqual(parse_weekly("Sun 12:30am"), (6, 0, 30))
        self.assertEqual(parse_weekly("monday 12pm"), (0, 12, 0))
        self.assertEqual(parse_weekly("Fri 09:05"), (4, 9, 5))

    def test_mistakes(self):
        for text in ["Wednesday", "17:00", "We 17:00", "Wed 25:00", "Wed 17:60", "Wed 13pm", "Wed 0am", "Wed 5",
                     "Wed 5:0", "Wed 17:00 every week", "Tu 5pm", "s 5pm"]:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "isn't a day and time"):
                parse_weekly(text)


class LoadAlertTestTest(unittest.TestCase):
    def test_defaults(self):
        settings = load_alert_test({}, "#storm")
        self.assertEqual(settings, TestSettings("#storm", "TEST: this is a test of the #storm alert channel. "
                                                          "No action needed.", None, None))

    def test_weekly_in_a_time_zone(self):
        settings = load_alert_test({"alert_test": {"weekly": "Wed 5:00PM", "timezone": "America/Chicago",
                                                   "message": "  Weekly net test  "}}, "#contingency-wx")
        self.assertEqual(settings, TestSettings("#contingency-wx", "Weekly net test", WED_5PM, CHICAGO))

    def test_mistakes_stop_startup(self):
        for section, problem in [
            ({"when": "Wed 17:00"}, "may only set message, timezone, weekly"),
            ({"weekly": "Wed"}, "isn't a day and time"),
            ({"weekly": 5}, "must be a day and time"),
            ({"timezone": "Central"}, "isn't a time zone"),
            ({"message": ""}, "must be some text"),
            ({"message": "x" * (MAX_REPLY_LEN + 1)}, f"at most {MAX_REPLY_LEN} characters"),
        ]:
            with self.subTest(section=section), self.assertRaisesRegex(SystemExit, problem):
                load_alert_test({"alert_test": section}, "#contingency-wx")


class NextWeeklyTest(unittest.TestCase):
    def test_later_this_week_or_next(self):
        tuesday = chicago(2026, 10, 20, 9, 0)
        self.assertEqual(next_weekly(WED_5PM, CHICAGO, tuesday), chicago(2026, 10, 21, 17, 0))
        wednesday_before = chicago(2026, 10, 21, 16, 59)
        self.assertEqual(next_weekly(WED_5PM, CHICAGO, wednesday_before), chicago(2026, 10, 21, 17, 0))
        on_time = chicago(2026, 10, 21, 17, 0)
        self.assertEqual(next_weekly(WED_5PM, CHICAGO, on_time), chicago(2026, 10, 28, 17, 0))

    def test_stays_at_5pm_across_daylight_saving(self):
        # Daylight saving ends on Sunday 1 November 2026: 5PM CDT one week, 5PM CST the next.
        after = next_weekly(WED_5PM, CHICAGO, chicago(2026, 10, 29, 12, 0))
        self.assertEqual(after, chicago(2026, 11, 4, 17, 0))
        self.assertEqual(after - chicago(2026, 10, 28, 17, 0), 7 * 86400 + 3600)
        self.assertEqual(when_text(chicago(2026, 10, 28, 17, 0), CHICAGO), "Wed 5:00PM CDT")
        self.assertEqual(when_text(after, CHICAGO), "Wed 5:00PM CST")

    def test_the_computers_own_time_zone(self):
        when = next_weekly(WED_5PM, None, time.time())
        local = datetime.datetime.fromtimestamp(when)
        self.assertEqual((local.weekday(), local.hour, local.minute), WED_5PM)
        self.assertLessEqual(when - time.time(), 7 * 86400 + 3600)


class AlertTestTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))
        self.radio = FakeMeshCore()
        self.state = State(self.folder)
        self.test = self.state.alert_test = AlertTest(
            self.radio, TestSettings("#contingency-wx", "Weekly test", WED_5PM, CHICAGO), self.state)
        self.cmd = TestAlertCommand(make_context("testalert", radio=self.radio, state=self.state))

    def history(self):
        return [(e["by"], e["what"]) for e in State(self.folder).store(HISTORY_FILE).data["entries"]]

    async def test_command_posts_the_test_now(self):
        with mock.patch("mesh_contingency.alerts.time.time", return_value=chicago(2026, 10, 20, 9, 0)):
            result = await self.cmd.execute("", ADMIN)
        self.assertEqual(self.radio.channel_sent, [(1, "Weekly test")])
        self.assertEqual(result.reply, "testalert: posted to #contingency-wx; next weekly test Wed 5:00PM CDT")
        self.assertEqual(result.console,
                         "Alert test posted to #contingency-wx (slot 1, added to the radio):\n  Weekly test")
        self.assertEqual(self.history(), [("Admin", "posted the alert test to #contingency-wx")])
        self.assertIn("last_test", State(self.folder).store(ALERTS_FILE).data)

    async def test_the_watched_counties_follow_the_message(self):
        names = ["Taylor", "Brown", "Callahan", "Coleman", "Comanche", "Eastland", "Fisher", "Haskell", "Jones",
                 "Kent", "Knox", "Mitchell", "Nolan", "Runnels", "Scurry", "Shackelford", "Stephens", "Stonewall",
                 "Throckmorton"]
        self.radio.self_info["name"] = "Hilltop Node"
        self.state.alert_test = AlertTest(self.radio, TestSettings("#contingency-wx", "Weekly test"), self.state,
                                          tuple(f"{n}, TX" for n in names))
        result = await self.cmd.execute("", ADMIN)
        sent = [text for _, text in self.radio.channel_sent]
        self.assertEqual(sent[0], "Weekly test")
        self.assertTrue(sent[1].startswith("(1/2) Counties watched for alerts: Taylor, Brown, "), sent)
        self.assertTrue(sent[2].startswith("(2/2) ") and sent[2].endswith(", Stonewall, Throckmorton"), sent)
        self.assertEqual(", ".join(sent[1:]).count(", TX"), 0)  # no states
        self.assertTrue(all(len(m) <= MAX_REPLY_LEN - len("Hilltop Node: ") for m in sent))
        for name in names:
            self.assertIn(name, " ".join(sent[1:]))
        self.assertIn("  (2/2) ", result.console)

    async def test_one_county_fits_in_one_message(self):
        self.state.alert_test = AlertTest(self.radio, TestSettings("#contingency-wx", "Test"), self.state,
                                          ("Taylor, TX",))
        await self.cmd.execute("", ADMIN)
        self.assertEqual([t for _, t in self.radio.channel_sent], ["Test", "Counties watched for alerts: Taylor"])

    async def test_command_without_a_weekly_test(self):
        self.state.alert_test = AlertTest(self.radio, TestSettings("#contingency-wx", "Test"), self.state)
        result = await self.cmd.execute("", ADMIN)
        self.assertEqual(result.reply, "testalert: posted to #contingency-wx")

    async def test_command_mistakes(self):
        with self.assertRaisesRegex(CommandError, r"^usage: testalert$"):
            await self.cmd.execute("now", ADMIN)
        self.radio.channels[1:] = [(f"ch{i}", bytes([i]) * 16) for i in range(1, 8)]
        with self.assertRaisesRegex(CommandError, "^testalert: no free channel slot on the radio for #contingency-wx$"):
            await self.cmd.execute("", ADMIN)
        self.state.alert_test = None
        with self.assertRaisesRegex(CommandError, "isn't set up"):
            await self.cmd.execute("", ADMIN)
        self.assertEqual(self.radio.channel_sent, [])

    async def test_a_message_too_long_for_this_node(self):
        self.radio.self_info["name"] = "N" * 40
        long = AlertTest(self.radio, TestSettings("#contingency-wx", "x" * 100), self.state)
        self.assertEqual(long.problem(), "[alert_test] message is 100 characters; a channel message from this node "
                                         f"has room for {MAX_REPLY_LEN - 42}")
        self.state.alert_test = long
        with self.assertRaisesRegex(CommandError, "message is 100 characters"):
            await self.cmd.execute("", ADMIN)
        self.assertIsNone(self.test.problem())

    async def test_describe(self):
        with mock.patch("mesh_contingency.alerts.time.time", return_value=chicago(2026, 10, 22, 9, 0)):
            self.assertEqual(self.test.describe(),
                             "Wednesday 17:00 America/Chicago to #contingency-wx; next Wed 5:00PM CDT")

    async def test_runs_every_week_at_the_time(self):
        clock = [chicago(2026, 10, 20, 9, 0)]  # a Tuesday morning
        sleeps = []

        async def sleep(seconds):
            sleeps.append(seconds)
            clock[0] += seconds
            if len(self.radio.channel_sent) == 2 and clock[0] > chicago(2026, 10, 28, 17, 0):
                raise asyncio.CancelledError

        with mock.patch("mesh_contingency.alerts.time.time", lambda: clock[0]), \
                mock.patch("mesh_contingency.alerts.asyncio.sleep", sleep), \
                mock.patch("mesh_contingency.state.time.time", lambda: clock[0]), \
                self.assertRaises(asyncio.CancelledError):
            await self.test.run()
        self.assertEqual(self.radio.channel_sent, [(1, "Weekly test")] * 2)
        self.assertTrue(all(s <= 3600 for s in sleeps))  # looks at the clock at least hourly
        times = [e["time"] for e in State(self.folder).store(HISTORY_FILE).data["entries"]]
        self.assertEqual(times, [chicago(2026, 10, 21, 17, 0), chicago(2026, 10, 28, 17, 0)])
        self.assertEqual(self.history(), [("auto", "posted the alert test to #contingency-wx")] * 2)
        self.assertIn("Weekly alert test posted to #contingency-wx:\n  Weekly test\n", self.out.getvalue())

    async def test_a_failed_week_doesnt_stop_it(self):
        clock = [chicago(2026, 10, 21, 16, 0)]
        self.radio.channel_result = event(EventType.ERROR, {"reason": "busy"})

        async def sleep(seconds):
            clock[0] += seconds
            if clock[0] > chicago(2026, 10, 21, 18, 0):
                raise asyncio.CancelledError

        with mock.patch("mesh_contingency.alerts.time.time", lambda: clock[0]), \
                mock.patch("mesh_contingency.alerts.asyncio.sleep", sleep), \
                self.assertRaises(asyncio.CancelledError):
            await self.test.run()
        self.assertIn("Weekly alert test failed: radio rejected channel message 1 of 1", self.out.getvalue())
        self.assertEqual(self.state.counts["errors"], 1)


if __name__ == "__main__":
    unittest.main()
