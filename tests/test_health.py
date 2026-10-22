import asyncio
import datetime
import tempfile
import time
import unittest
import zoneinfo
from pathlib import Path
from unittest import mock

from meshcore import EventType

from mesh_contingency.alerts import AlertSettings, AlertTest, AlertWatcher, TestSettings
from mesh_contingency.api import MAX_REPLY_LEN, CommandError
from mesh_contingency.commands import health
from mesh_contingency.commands.health import HealthCommand
from mesh_contingency.directory import Directory, DirectoryError
from mesh_contingency.limits import Limits
from mesh_contingency.state import State, duration
from mesh_contingency.testing import FakeMeshCore, event, make_context

ALICE = "a1" * 32
BOB = "b0" * 32


class DurationTest(unittest.TestCase):
    def test_two_largest_units(self):
        self.assertEqual(duration(0), "0m")
        self.assertEqual(duration(59), "0m")
        self.assertEqual(duration(12 * 60 + 5), "12m")
        self.assertEqual(duration(3 * 3600 + 5 * 60), "3h 5m")
        self.assertEqual(duration(2 * 86400 + 3 * 3600 + 59), "2d 3h")


class HealthTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.radio = FakeMeshCore({"a1a1": "Alice", "b0b0": "Bob"})
        self.radio.self_info["name"] = "Node"
        self.state = State()
        self.directory = Directory({ALICE: {"name": "Alice"}, BOB: {"name": "Bob"}}, {ALICE})
        self.health = HealthCommand(make_context("health", radio=self.radio, state=self.state,
                                                 directory=self.directory, limits=Limits(emails_per_day_total=200)))

    async def reply(self):
        result = await self.health.execute("", None)
        for message in result.reply:
            self.assertLessEqual(len(message), MAX_REPLY_LEN)
        return " ".join(result.reply)

    async def test_a_quiet_node(self):
        self.state.started = time.time() - 3 * 3600 - 300
        text = await self.reply()
        for part in ["health: up 3h 5m", "radio Node (Test Board v1.9)", "radio up 1d 2h", "battery 4.05V",
                     "contacts 2/350", "users 2 (1 admin)", "join requests 0", "inbox 0 message(s) for 0 user(s)",
                     "check-ins 0", "since start 0 message(s) in, 0 out (0 undelivered)", "errors none",
                     "emails 24h 0/200 address(es)", "no flood advert yet"]:
            self.assertIn(part, text)

    async def test_a_busy_node(self):
        self.state.store("mailbox.json").data.update({ALICE: [{}, {}], BOB: [{}], "cc" * 32: []})
        self.state.store("requests.json").data["dd" * 32] = {"name": "Dee", "time": 0}
        self.state.store("status.json").data.update({ALICE: {}, BOB: {}})
        self.state.store("adverts.json").data["last_flood"] = time.time() - 7200
        self.state.counts.update(messages=12, sent=15, undelivered=2)
        self.state.error("wx timed out")
        self.state.emails.record(ALICE, 3)
        text = await self.reply()
        for part in ["join requests 1", "inbox 3 message(s) for 2 user(s)", "check-ins 2",
                     "since start 12 message(s) in, 15 out (2 undelivered)", "errors 1, last wx timed out just now",
                     "emails 24h 3/200 address(es)", "last flood advert 2h ago"]:
            self.assertIn(part, text)

    async def test_last_email_failure(self):
        self.assertNotIn("last email failed", await self.reply())
        self.state.emails.last_failure = (time.time() - 300, "no internet at the node")
        self.assertIn("last email failed 5m ago: no internet at the node", await self.reply())

    async def test_auto_alerts(self):
        text = await self.reply()
        self.assertNotIn("auto alerts", text)
        watcher = self.state.alert_watcher = AlertWatcher(self.radio, AlertSettings(("Taylor, TX", "Jones, TX")),
                                                          self.state)
        self.assertIn("auto alerts 2 counties, not checked yet", await self.reply())
        watcher.last_check = time.time() - 180
        watcher.problem = "timed out"
        watcher.unmapped["Jones, TX"] = "timed out"
        self.assertIn("auto alerts 2 counties, checked 3m ago, last check failed, not looked up: Jones, TX",
                      await self.reply())

    async def test_next_alert_test(self):
        self.state.alert_test = AlertTest(self.radio, TestSettings("#contingency-wx", "Test"), self.state)
        self.assertNotIn("alert test", await self.reply())  # not weekly
        chicago = zoneinfo.ZoneInfo("America/Chicago")
        self.state.alert_test = AlertTest(self.radio, TestSettings("#contingency-wx", "Test", (2, 17, 0), chicago),
                                          self.state)
        tuesday = datetime.datetime(2026, 10, 20, 9, 0, tzinfo=chicago).timestamp()
        with mock.patch("mesh_contingency.alerts.time.time", return_value=tuesday):
            self.assertIn("next alert test Wed 5:00PM CDT", await self.reply())

    async def test_what_the_radio_doesnt_answer_is_left_out(self):
        self.radio.device_info = {}
        self.radio.battery_result = event(EventType.ERROR, {"reason": "unsupported"})
        self.radio.stats_result = event(EventType.ERROR, {"reason": "unsupported"})
        text = await self.reply()
        self.assertIn("radio Node; contacts 2;", text)
        self.assertNotIn("battery", text)
        self.assertNotIn("radio up", text)

    async def test_battery_from_stats_when_get_bat_fails(self):
        self.radio.battery_result = event(EventType.ERROR)
        self.assertIn("battery 4.05V", await self.reply())

    async def test_a_radio_that_doesnt_answer_doesnt_hold_it_up(self):
        async def never():
            await asyncio.Event().wait()

        self.radio.commands.get_bat = never
        self.radio.commands.get_stats_core = never
        with mock.patch.object(health, "RADIO_SECONDS", 0.01):
            text = await self.reply()
        self.assertIn("radio Node (Test Board v1.9); contacts 2/350", text)
        self.assertNotIn("battery", text)

    async def test_users_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "users.toml"
            path.write_text(f'[admin]\nkeys = ["{ALICE}"]\n')
            self.health.ctx.directory = directory = Directory(path=path)
            directory.load()
            self.assertIn("users.toml loaded just now", await self.reply())
            path.write_text("not toml [")
            with self.assertRaises(DirectoryError):
                directory.check(force=True)
            self.assertRegex(await self.reply(), r"users\.toml NOT reloaded just now: not valid TOML")
            path.write_text(f'[admin]\nkeys = ["{ALICE}"]\n')
            directory.check(force=True)
            text = await self.reply()
            self.assertIn("users.toml loaded just now", text)
            self.assertNotIn("NOT reloaded", text)

    async def test_no_arguments(self):
        with self.assertRaisesRegex(CommandError, r"^usage: health$"):
            await self.health.execute("now", None)


if __name__ == "__main__":
    unittest.main()
