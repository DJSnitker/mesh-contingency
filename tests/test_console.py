import asyncio
import contextlib
import io
import os
import pty
import tempfile
import unittest
from unittest import mock

from meshcore import EventType

from mesh_contingency.console import (
    HELP,
    RETRY_SECONDS,
    advert_on_schedule,
    list_contacts,
    load_advert,
    record_advert,
    run_console_command,
    seconds_until_advert,
    watch_console,
)
from mesh_contingency.state import Store
from mesh_contingency.testing import FakeMeshCore, event


class LoadAdvertTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(load_advert({}), (False, 0, True))

    def test_settings(self):
        self.assertEqual(load_advert({"advert": {"at_startup": True, "every_hours": 12, "flood": False}}),
                         (True, 12, False))
        self.assertEqual(load_advert({"advert": {"every_hours": 0.5}})[1], 0.5)

    def test_mistakes(self):
        for section, error in [({"often": 1}, "may only set"), ({"at_startup": "yes"}, "true or false"),
                               ({"flood": 1}, "true or false"), ({"every_hours": -1}, "every_hours must be"),
                               ({"every_hours": True}, "every_hours must be")]:
            with self.subTest(section=section), self.assertRaisesRegex(SystemExit, error):
                load_advert({"advert": section})


class ConsoleCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.radio = FakeMeshCore({"a1b2c3d4e5f6": "Alice", "b0b0b0b0b0b0": "Bob"})

    async def run_line(self, line):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            await run_console_command(self.radio, line)
        return out.getvalue()

    async def test_adverts(self):
        self.assertEqual(await self.run_line("advert\n"), "Sent zero-hop advert (console)\n")
        self.assertEqual(await self.run_line("ADVERT flood"), "Sent flood advert (console)\n")
        self.assertEqual(self.radio.adverts, [False, True])

    async def test_advert_refused_by_the_radio(self):
        self.radio.advert_result = event(EventType.ERROR, {"reason": "busy"})
        self.assertIn("Advert failed (console): radio rejected flood advert", await self.run_line("advert flood"))

    async def test_contacts(self):
        out = await self.run_line("contacts")
        self.assertTrue(out.startswith("2 contact(s):\n  a1b2c3d4e5f6  Alice\n  b0b0b0b0b0b0  Bob"))
        self.assertEqual(await self.run_line("contacts bo"), "1 contact(s) matching bo:\n  b0b0b0b0b0b0  Bob\n")
        self.assertEqual(list_contacts(self.radio, "a1b2"), "1 contact(s) matching a1b2:\n  a1b2c3d4e5f6  Alice")
        self.assertEqual(list_contacts(self.radio, "zed"), "0 contact(s) matching zed:")

    async def test_help_and_unknown(self):
        self.assertEqual(await self.run_line("help"), HELP + "\n")
        self.assertIn("Unknown console command: advert now\n", await self.run_line("advert now"))
        self.assertEqual(await self.run_line("   \n"), "")
        self.assertEqual(self.radio.adverts, [])


class ScheduleTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = 1_000_000.0
        self.enterContext(mock.patch("mesh_contingency.console.time.time", lambda: self.now))
        self.folder = self.enterContext(tempfile.TemporaryDirectory())
        self.store = Store(os.path.join(self.folder, "adverts.json"))
        self.radio = FakeMeshCore()
        self.sleeps = []

    async def fake_sleep(self, seconds):
        """Record the wait and move the clock on, stopping after a few waits."""
        self.sleeps.append(seconds)
        self.now += seconds
        if len(self.sleeps) >= 3:
            raise asyncio.CancelledError

    async def run_schedule(self):
        with mock.patch("mesh_contingency.console.asyncio.sleep", self.fake_sleep), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.suppress(asyncio.CancelledError):
            await advert_on_schedule(self.radio, self.store, 12, True)

    def test_seconds_until_advert(self):
        self.assertEqual(seconds_until_advert(self.store, 12, True), 0)  # never adverted
        record_advert(self.store, True)
        self.now += 3600
        self.assertEqual(seconds_until_advert(self.store, 12, True), 11 * 3600)
        self.assertEqual(seconds_until_advert(Store(self.store.path), 12, True), 11 * 3600)  # read back from the file
        self.assertEqual(seconds_until_advert(self.store, 12, False), 0)  # zero-hop is counted apart
        self.now += 12 * 3600
        self.assertEqual(seconds_until_advert(self.store, 12, True), 0)  # overdue

    async def test_overdue_adverts_at_once_then_every_12_hours(self):
        await self.run_schedule()
        self.assertEqual(self.radio.adverts, [True, True, True])
        self.assertEqual(self.sleeps, [12 * 3600, 12 * 3600, 12 * 3600])
        self.assertEqual(Store(self.store.path).data["last_flood"], self.now - 12 * 3600)

    async def test_restart_waits_for_the_rest_of_the_interval(self):
        record_advert(self.store, True)
        self.now += 5 * 3600  # restarted 5 hours after the last advert
        await self.run_schedule()
        self.assertEqual(self.sleeps[0], 7 * 3600)
        self.assertEqual(len(self.radio.adverts), 2)

    async def test_refused_advert_is_retried_and_not_recorded(self):
        self.radio.advert_result = event(EventType.ERROR, {"reason": "busy"})
        await self.run_schedule()
        self.assertEqual(self.sleeps, [RETRY_SECONDS] * 3)
        self.assertNotIn("last_flood", self.store.data)

    async def test_advert_by_hand_moves_the_schedule(self):
        record_advert(self.store, True)

        async def advert_by_hand_while_waiting(seconds):
            if not self.sleeps:  # 4 hours into the first wait, someone sends one by hand
                self.now += 4 * 3600
                with contextlib.redirect_stdout(io.StringIO()):
                    await run_console_command(self.radio, "advert flood", self.store)
                self.now += seconds - 4 * 3600
                self.sleeps.append(seconds)
                return
            await self.fake_sleep(seconds)

        with mock.patch("mesh_contingency.console.asyncio.sleep", advert_by_hand_while_waiting), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.suppress(asyncio.CancelledError):
            await advert_on_schedule(self.radio, self.store, 12, True)
        # It waited out the first 12 hours, saw the advert sent by hand, then
        # waited the 4 hours left until 12 hours after that one.
        self.assertEqual(self.sleeps[:2], [12 * 3600, 4 * 3600])


class WatchConsoleTest(unittest.IsolatedAsyncioTestCase):
    async def test_no_terminal(self):
        self.assertIsNone(watch_console(asyncio.get_running_loop(), print, stdin=io.StringIO()))

    async def test_reads_lines_typed_into_a_terminal(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        stdin = open(slave, encoding="utf-8")
        self.addCleanup(stdin.close)
        lines = asyncio.Queue()
        stop = watch_console(asyncio.get_running_loop(), lines.put_nowait, stdin=stdin)
        self.addCleanup(stop)
        os.write(master, b"advert flood\n")
        self.assertEqual(await asyncio.wait_for(lines.get(), 2), "advert flood\n")


if __name__ == "__main__":
    unittest.main()
