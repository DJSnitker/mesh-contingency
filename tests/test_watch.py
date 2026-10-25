import io
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from meshcore import EventType

from mesh_contingency.api import Sender
from mesh_contingency.commands.email import EmailCommand
from mesh_contingency.commands.health import HealthCommand
from mesh_contingency.commands.mail import ADDRESS_REFUSED, NO_INTERNET, SendError
from mesh_contingency.directory import Directory
from mesh_contingency.state import State
from mesh_contingency.testing import FakeMeshCore, event, make_context
from mesh_contingency.watch import NOTICE_GAP, NodeWatch, WatchSettings, load_watch

ADMIN = "a1" * 32
DANA = Sender("Dana", "d0" * 32)


class LoadWatchTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(load_watch({}), WatchSettings(True, 5, 3.5, 5, 3))

    def test_settings(self):
        settings = load_watch({"watch": {"enabled": False, "every_minutes": 2, "battery_volts": 3.4,
                                         "undelivered_in_row": 0, "errors": 10}})
        self.assertEqual(settings, WatchSettings(False, 2, 3.4, 0, 10))

    def test_mistakes(self):
        for section, message in [
            ({"battery": 3}, r"^\[watch\] may only set battery_volts, enabled, errors, every_minutes, "
                             r"undelivered_in_row\.$"),
            ({"enabled": "yes"}, r"enabled must be true or false"),
            ({"every_minutes": 0.5}, r"every_minutes must be a number, at least 1\."),
            ({"battery_volts": -1}, r"battery_volts must be a number, at least 0\."),
            ({"undelivered_in_row": 2.5}, r"undelivered_in_row must be a whole number, at least 0\."),
            ({"errors": True}, r"errors must be a whole number"),
        ]:
            with self.assertRaisesRegex(SystemExit, message):
                load_watch({"watch": section})


class NodeWatchTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.now = 1_000_000.0
        self.enterContext(mock.patch("mesh_contingency.watch.time.time", lambda: self.now))
        self.booted = 0.0  # when the computer started: long before the radio, unless a test says
        self.enterContext(mock.patch("mesh_contingency.watch.computer_started", lambda: self.booted))
        self.radio = FakeMeshCore()
        self.uptime = 3600
        self.volts(4.1)
        self.directory = Directory({}, {ADMIN})
        self.notices = []
        self.watch = self.new_watch()

    def new_watch(self, settings=None):
        """A watch as after a restart of the bot: new state, same files."""
        self.state = State(self.folder)
        self.state.started = self.now
        return NodeWatch(self.radio, settings or WatchSettings(), self.state, self.directory, self.notices.append)

    def volts(self, volts):
        self.radio.battery_result = event(EventType.BATTERY, {"level": int(volts * 1000)})

    async def check(self, minutes=5):
        """Let `minutes` pass, then check; return the notices sent."""
        self.now += minutes * 60
        self.uptime += minutes * 60
        self.radio.stats_result = event(EventType.STATS_CORE, {"uptime_secs": self.uptime})
        start = len(self.notices)
        await self.watch.check()
        return self.notices[start:]

    async def test_quiet_node_sends_nothing(self):
        self.assertEqual(await self.check(), [])
        self.assertEqual(await self.check(), [])
        self.assertEqual(self.watch.active, [])

    async def test_battery_low_then_ok_again(self):
        await self.check()
        self.volts(3.42)
        self.assertEqual(await self.check(), ["Node problem: battery low, 3.42V (below 3.50V)"])
        self.assertEqual(await self.check(), [])  # told once
        self.volts(3.55)  # above the threshold, but not by the margin: no flapping
        self.assertEqual(await self.check(), [])
        self.assertEqual(self.watch.active, ["battery"])
        self.volts(3.65)
        self.assertEqual(await self.check(), ["Node ok again: battery 3.65V"])
        self.assertEqual(self.watch.active, [])

    async def test_battery_unknown_changes_nothing(self):
        self.volts(3.4)
        await self.check()
        self.radio.battery_result = None
        self.radio.stats_result = event(EventType.STATS_CORE, {})
        await self.watch.check()
        self.assertEqual(self.watch.active, ["battery"])
        self.assertEqual(len(self.notices), 1)

    async def test_battery_check_off(self):
        self.watch = self.new_watch(WatchSettings(battery_volts=0))
        self.volts(3.0)
        self.assertEqual(await self.check(), [])

    async def test_a_problem_comes_back_within_the_hour(self):
        self.volts(3.4)
        await self.check()
        self.volts(3.7)
        self.assertEqual(await self.check(), ["Node ok again: battery 3.70V"])
        self.volts(3.4)
        self.assertEqual(await self.check(), [])  # announced 10 min ago: not again
        self.volts(3.7)
        self.assertEqual(await self.check(), [])  # and so no "ok again" either
        self.volts(3.4)
        self.assertEqual(await self.check(NOTICE_GAP / 60), ["Node problem: battery low, 3.40V (below 3.50V)"])

    async def test_ongoing_problem_not_announced_again_after_a_restart(self):
        self.volts(3.4)
        self.assertEqual(len(await self.check()), 1)
        self.watch = self.new_watch()
        self.assertEqual(await self.check(), [])
        self.volts(3.8)
        self.assertEqual(await self.check(), ["Node ok again: battery 3.80V"])

    async def test_radio_restart(self):
        self.assertEqual(await self.check(), [])  # the first check only notes when it started
        self.uptime = 0
        self.assertEqual(await self.check(3),
                         ["Node problem: the radio restarted 3m ago (power, USB or a crash)"])
        self.assertEqual(await self.check(), [])
        self.uptime = 0
        self.assertEqual(await self.check(), [])  # again within the hour: the console only

    async def test_radio_restart_that_restarted_the_bot_too(self):
        await self.check()
        self.watch = self.new_watch()  # e.g. the USB cable was pulled, and the bot exited
        self.uptime = 0
        self.assertEqual(await self.check(1), ["Node problem: the radio restarted 1m ago (power, USB or a crash)"])

    async def test_radio_restart_with_the_computer(self):
        await self.check()
        self.watch = self.new_watch()  # the computer rebooted, and the bot started with it
        self.booted = self.now + 60
        self.uptime = -60  # USB power came back a minute later, and the radio started
        self.assertEqual(await self.check(2), ["Node restarted: the computer started 1m ago, and the radio with it"])

    async def test_radio_restart_long_after_the_computer_is_still_a_problem(self):
        self.booted = self.now - 3600
        await self.check()
        self.uptime = 0
        self.assertEqual(await self.check(1), ["Node problem: the radio restarted 1m ago (power, USB or a crash)"])

    async def test_radio_restart_where_the_computer_cant_say_when_it_started(self):
        await self.check()
        self.booted = None
        self.uptime = 0
        self.assertEqual(await self.check(1), ["Node problem: the radio restarted 1m ago (power, USB or a crash)"])

    async def test_bot_restart_alone_is_not_a_radio_restart(self):
        await self.check()
        self.watch = self.new_watch()
        self.assertEqual(await self.check(1), [])

    async def test_undelivered_in_a_row(self):
        self.state.undelivered_in_row = 4
        self.assertEqual(await self.check(), [])
        self.state.undelivered_in_row = 5
        self.assertEqual(await self.check(), ["Node problem: 5 messages in a row not delivered"])
        self.state.undelivered_in_row = 6
        self.assertEqual(await self.check(), [])
        with mock.patch("mesh_contingency.state.time.time", lambda: self.now + 1):
            self.state.delivered()
        self.assertEqual(await self.check(), ["Node ok again: messages delivered"])

    async def test_email_failing(self):
        self.state.emails.failing = "no internet at the node"
        self.assertEqual(await self.check(), ["Node problem: email failing: no internet at the node"])
        self.state.emails.failing = None
        self.state.emails.last_sent = self.now + 1
        self.assertEqual(await self.check(), ["Node ok again: an email was sent"])
        self.assertEqual(self.watch.active, [])

    async def test_a_bot_restart_doesnt_end_a_problem(self):
        """2026-10-22: after a restart the email problem was said to be over,
        though no email had been sent."""
        self.state.emails.failing = "no internet at the node"
        self.state.undelivered_in_row = 5
        self.state.backups = mock.Mock(failing="No space left on device", last=None,
                                       settings=mock.Mock(to="/mnt/usb"))
        self.assertEqual(len(await self.check()), 3)
        backups = self.state.backups
        self.watch = self.new_watch()  # remembers nothing it had seen
        self.state.backups = mock.Mock(failing=None, last=backups.last, settings=backups.settings)
        self.assertEqual(await self.check(), [])
        self.assertEqual(sorted(self.watch.active), ["backup", "email", "undelivered"])
        self.state.emails.last_sent = self.now + 1  # an email goes out
        self.state.backups.last = self.now + 1  # and a backup is made
        self.assertEqual(await self.check(), ["Node ok again: an email was sent", "Node ok again: a backup was made"])
        self.assertEqual(self.watch.active, ["undelivered"])

    async def test_radio_lost_then_back(self):
        await self.check()
        self.watch.lost_radio("reconnect_failed")
        self.now += 7 * 60  # unplugged for 7 minutes, the radio running on its battery
        self.uptime += 7 * 60
        self.watch = self.new_watch()
        self.assertEqual(await self.check(0),
                         ["Node problem: the radio was disconnected for 7m (reconnect_failed); back now"])
        self.assertEqual(await self.check(), [])  # said once

    async def test_radio_lost_is_told_only_after_a_restart(self):
        await self.check()
        self.watch.lost_radio("reconnect_failed")  # the bot is stopping
        self.assertEqual(await self.check(0), [])  # a check before it does says nothing
        self.assertIn("lost", self.watch.store.data)
        self.now += 60
        self.uptime += 60
        self.watch = self.new_watch()
        self.assertEqual(await self.check(0),
                         ["Node problem: the radio was disconnected for 1m (reconnect_failed); back now"])

    async def test_a_reboot_from_the_console_is_only_logged(self):
        await self.check()
        self.watch.rebooting("the radio was rebooted from the console")
        self.now += 30
        self.watch = self.new_watch()  # the bot restarted with it
        self.uptime = -30  # the radio started about when the bot did
        out = self.enterContext(mock.patch("sys.stdout", new_callable=io.StringIO))
        self.assertEqual(await self.check(1), [])
        self.assertIn("Watch: the radio restarted just now: the radio was rebooted from the console", out.getvalue())
        self.assertNotIn("rebooting", self.watch.store.data)
        self.assertEqual(await self.check(), [])
        self.uptime = 0  # a later restart is news again
        self.assertEqual(await self.check(1), ["Node problem: the radio restarted 1m ago (power, USB or a crash)"])

    async def test_a_reboot_asked_for_counts_only_for_the_next_run(self):
        await self.check()
        self.watch.rebooting("the radio was rebooted from the console")
        self.assertEqual(await self.check(0), [])  # this run: not used up
        self.assertIn("rebooting", self.watch.store.data)
        self.now += 30
        self.watch = self.new_watch()
        self.assertEqual(await self.check(1), [])  # the radio didn't restart after all: forgotten
        self.assertNotIn("rebooting", self.watch.store.data)
        self.watch = self.new_watch()
        self.uptime = 0
        self.assertEqual(await self.check(1), ["Node problem: the radio restarted 1m ago (power, USB or a crash)"])

    async def test_radio_lost_and_restarted(self):
        await self.check()
        self.watch.lost_radio("reconnect_failed")
        self.now += 3 * 60
        self.watch = self.new_watch()
        self.uptime = 0  # no battery: it restarted when plugged back in
        self.assertEqual(await self.check(1), ["Node problem: the radio was disconnected for 4m "
                                               "(reconnect_failed), and it restarted; back now"])

    async def test_radio_lost_as_the_computer_shut_down(self):
        await self.check()
        self.watch.lost_radio("reconnect_failed")  # its USB went first, then the bot was stopped
        self.booted = self.now + 5 * 3600 + 25 * 60  # off for 5h 25m
        self.now = self.booted + 10 * 60  # the radio was found 10 minutes after the computer started
        self.watch = self.new_watch()
        self.uptime = -9 * 60  # USB power came back with the computer
        self.assertEqual(await self.check(0), ["Node restarted: the computer started 10m ago; "
                                               "the radio was lost 5h 25m before (reconnect_failed)"])
        self.assertNotIn("lost", self.watch.store.data)
        self.assertEqual(await self.check(), [])  # said once

    async def test_radio_lost_where_the_computer_cant_say_when_it_started(self):
        await self.check()
        self.watch.lost_radio("reconnect_failed")
        self.booted = None
        self.now += 3 * 60
        self.uptime += 3 * 60
        self.watch = self.new_watch()
        self.assertEqual(await self.check(0),
                         ["Node problem: the radio was disconnected for 3m (reconnect_failed); back now"])

    async def test_radio_lost_again_within_the_hour(self):
        await self.check()
        for minutes in (2, 3):
            self.watch.lost_radio("reconnect_failed")
            self.now += minutes * 60
            self.uptime += minutes * 60
            self.watch = self.new_watch()
            await self.check(0)
        self.assertEqual(self.notices, ["Node problem: the radio was disconnected for 2m (reconnect_failed); back now"])

    async def test_repeated_errors(self):
        with mock.patch("mesh_contingency.state.time.time", lambda: self.now):
            self.state.error("wx timed out")
            self.state.error("wx timed out")
            self.assertEqual(await self.check(), [])
            self.state.error("wx failed")
            self.assertEqual(await self.check(1), ["Node problem: 3 command errors in 30 min, last wx failed"])
            self.assertEqual(await self.check(20), [])
            self.assertEqual(await self.check(10), ["Node ok again: no more command errors"])

    async def test_errors_after_a_restart_end_after_the_window(self):
        with mock.patch("mesh_contingency.state.time.time", lambda: self.now):
            for _ in range(3):
                self.state.error("wx failed")
        self.assertEqual(len(await self.check(1)), 1)
        self.watch = self.new_watch()  # no errors remembered
        self.assertEqual(await self.check(10), [])
        self.assertEqual(await self.check(20), ["Node ok again: no more command errors"])

    async def test_users_file(self):
        self.directory.problem = (self.now, "[users]: 'd0d0' is not a full public key")
        self.assertEqual(await self.check(),
                         ["Node problem: users.toml not reloaded: [users]: 'd0d0' is not a full public key"])
        self.directory.problem = None
        self.assertEqual(await self.check(), ["Node ok again: users.toml reloaded"])

    async def test_describe(self):
        self.assertEqual(self.watch.describe(), "every 5 min: battery below 3.5V, radio restarts, "
                                                "5 undelivered in a row, email failing, 3 errors in 30 min, "
                                                "users.toml not reloading")
        self.watch = self.new_watch(WatchSettings(battery_volts=0, undelivered_in_row=0, errors=0))
        self.assertEqual(self.watch.describe(), "every 5 min: radio restarts, email failing, "
                                                "users.toml not reloading")

    async def test_in_health(self):
        self.state.watch = self.watch
        health = HealthCommand(make_context("health", radio=self.radio, state=self.state, directory=self.directory))
        await self.check()
        self.assertIn("watch: no problems", " ".join((await health.execute("", None)).reply))
        self.volts(3.3)
        self.state.emails.failing = "no internet at the node"
        await self.check()
        self.assertIn("watch: battery low, email failing", " ".join((await health.execute("", None)).reply))


class EmailFailingTest(unittest.IsolatedAsyncioTestCase):
    async def test_only_the_nodes_own_failures_count(self):
        state = State()
        email = EmailCommand(make_context("email", state=state))
        with mock.patch("mesh_contingency.commands.mail.send_email") as send_email:
            send_email.side_effect = SendError("refused", ADDRESS_REFUSED)
            with self.assertRaises(SendError):
                await email.execute("x@example.com hi", DANA)
            self.assertIsNone(state.emails.failing)
            send_email.side_effect = SendError("no route", NO_INTERNET)
            with self.assertRaises(SendError):
                await email.execute("x@example.com hi", DANA)
            self.assertEqual(state.emails.failing, "no internet at the node")
            send_email.side_effect = None
            await email.execute("x@example.com hi", DANA)
            self.assertIsNone(state.emails.failing)


class RecentErrorsTest(unittest.TestCase):
    def test_counts_within_the_window(self):
        state = State()
        now = time.time()
        with mock.patch("mesh_contingency.state.time.time", side_effect=[now - 3600, now - 600, now - 60]):
            for _ in range(3):
                state.error("wx failed")
        self.assertEqual(state.recent_errors(1800, now), 2)
        self.assertEqual(state.recent_errors(7200, now), 3)


if __name__ == "__main__":
    unittest.main()
