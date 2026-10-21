import contextlib
import io
import unittest

from mesh_contingency.alerts import AlertSettings, AlertWatcher
from mesh_contingency.api import CommandError, Sender
from mesh_contingency.commands.alertmap import AlertMapCommand
from mesh_contingency.state import HISTORY_FILE, State
from mesh_contingency.testing import FakeMeshCore, make_context

ADMIN = Sender("Admin", "ad" * 32)


class AlertMapTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.state = State()
        self.codes = {"Taylor, TX": "TXC441", "Jones, TX": "TXC253"}
        self.cmd = AlertMapCommand(make_context("alertmap", state=self.state))

    def lookup(self, name, state):
        found = self.codes[f"{name}, {state}"]
        if isinstance(found, Exception):
            raise found
        return found

    def watch(self, *counties):
        self.state.alert_watcher = AlertWatcher(FakeMeshCore(), AlertSettings(counties), self.state,
                                                lookup=self.lookup, fetch=lambda codes: [])

    async def test_looks_up_every_watched_county(self):
        self.watch("Taylor, TX", "Jones, TX")
        result = await self.cmd.execute("", ADMIN)
        self.assertEqual(result.reply, ["alertmap: Taylor, TX: TXC441", "alertmap: Jones, TX: TXC253"])
        self.assertEqual(set(self.state.alert_watcher.codes), {"Taylor, TX", "Jones, TX"})
        entries = self.state.store(HISTORY_FILE).data["entries"]
        self.assertEqual([(e["by"], e["what"]) for e in entries],
                         [("Admin", "looked up the NWS codes of Taylor, TX; Jones, TX")])

    async def test_one_county_however_its_written(self):
        self.watch("Taylor, TX", "Jones, TX")
        for text in ["Jones, TX", " jones tx ", "Jones County, TX"]:
            result = await self.cmd.execute(text, ADMIN)
            self.assertEqual(result.reply, ["alertmap: Jones, TX: TXC253"])
        self.assertEqual(set(self.state.alert_watcher.codes), {"Jones, TX"})

    async def test_a_lookup_that_fails(self):
        self.watch("Taylor, TX", "Jones, TX")
        self.codes["Jones, TX"] = OSError("timed out")
        result = await self.cmd.execute("", ADMIN)
        self.assertEqual(result.reply[1], "alertmap: Jones, TX: not looked up (timed out)")
        self.assertEqual(self.state.alert_watcher.unmapped, {"Jones, TX": "timed out"})

    async def test_mistakes(self):
        with self.assertRaisesRegex(CommandError, r"no counties are watched; set counties in \[alerts\]"):
            await self.cmd.execute("", ADMIN)
        self.watch("Taylor, TX")
        with self.assertRaisesRegex(CommandError, "Nolan, TX isn't watched; watched: Taylor, TX"):
            await self.cmd.execute("Nolan TX", ADMIN)
        with self.assertRaisesRegex(CommandError, r"'Taylor' isn't a county and state.*usage: alertmap \[county, ST\]"):
            await self.cmd.execute("Taylor", ADMIN)


if __name__ == "__main__":
    unittest.main()
