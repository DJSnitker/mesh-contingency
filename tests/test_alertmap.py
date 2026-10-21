import contextlib
import io
import unittest

from mesh_contingency.alerts import AlertSettings, AlertWatcher
from mesh_contingency.api import CommandError, Sender, to_messages
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
        self.assertEqual(result.reply, "alertmap: 2 looked up: Taylor, Jones")
        self.assertEqual(set(self.state.alert_watcher.codes), {"Taylor, TX", "Jones, TX"})
        entries = self.state.store(HISTORY_FILE).data["entries"]
        self.assertEqual([(e["by"], e["what"]) for e in entries],
                         [("Admin", "looked up the NWS codes of Taylor, TX; Jones, TX")])

    async def test_one_county_however_its_written(self):
        self.watch("Taylor, TX", "Jones, TX")
        for text in ["Jones, TX", " jones tx ", "Jones County, TX"]:
            result = await self.cmd.execute(text, ADMIN)
            self.assertEqual(result.reply, "alertmap: 1 looked up: Jones")
        self.assertEqual(set(self.state.alert_watcher.codes), {"Jones, TX"})

    async def test_a_lookup_that_fails(self):
        self.watch("Taylor, TX", "Jones, TX")
        self.codes["Jones, TX"] = OSError("timed out")
        result = await self.cmd.execute("", ADMIN)
        self.assertEqual(result.reply, "alertmap: 1 looked up: Taylor; not looked up: Jones (timed out)")
        self.codes["Taylor, TX"] = OSError("no network")
        result = await self.cmd.execute("", ADMIN)
        self.assertEqual(result.reply, "alertmap: not looked up: Taylor (no network), Jones (timed out)")
        self.assertEqual(self.state.alert_watcher.unmapped, {"Taylor, TX": "no network", "Jones, TX": "timed out"})

    async def test_many_counties_in_few_messages(self):
        names = ["Taylor", "Brown", "Callahan", "Coleman", "Comanche", "Eastland", "Fisher", "Haskell", "Jones",
                 "Kent", "Knox", "Mitchell", "Nolan", "Runnels", "Scurry", "Shackelford", "Stephens", "Stonewall",
                 "Throckmorton"]
        self.codes = {f"{n}, TX": f"TXC{i:03d}" for i, n in enumerate(names)}
        self.watch(*self.codes)
        messages = to_messages((await self.cmd.execute("", ADMIN)).reply)
        self.assertEqual(len(messages), 2)
        self.assertTrue(messages[0].startswith("(1/2) alertmap: 19 looked up: Taylor, Brown, "), messages)
        self.assertTrue(messages[1].endswith("Stonewall, Throckmorton"), messages)

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
