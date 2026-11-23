import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from mesh_commands import CommandError, Sender
from mesh_commands.testing import FakeMeshCore, event, make_context
from meshcore import EventType

from mesh_contingency.commands.advert import AdvertCommand
from mesh_contingency.console import ADVERTS_FILE, seconds_until_advert
from mesh_contingency.state import State

ADMIN = Sender("Admin", "ad" * 32)


class AdvertCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))
        self.radio = FakeMeshCore()
        self.state = State(self.folder)
        self.cmd = AdvertCommand(make_context("advert", radio=self.radio, extras={"state": self.state}))

    async def test_a_flood_advert_by_default(self):
        self.assertEqual(await self.cmd.execute("", ADMIN), "advert: sent a flood advert")
        self.assertEqual(self.radio.adverts, [True])
        self.assertIn("Sent flood advert (advert from Admin)", self.out.getvalue())

    async def test_flood_and_zero_hop(self):
        self.assertEqual(await self.cmd.execute(" FLOOD ", ADMIN), "advert: sent a flood advert")
        self.assertEqual(await self.cmd.execute("zero", ADMIN), "advert: sent a zero-hop advert")
        self.assertEqual(self.radio.adverts, [True, False])

    async def test_it_counts_towards_the_schedule(self):
        await self.cmd.execute("", ADMIN)
        store = State(self.folder).store(ADVERTS_FILE)
        self.assertGreater(seconds_until_advert(store, 12, True), 11.9 * 3600)
        self.assertEqual(seconds_until_advert(store, 12, False), 0)  # a zero-hop one is still due

    async def test_mistakes(self):
        with self.assertRaisesRegex(CommandError, r"^usage: advert \[zero\]$"):
            await self.cmd.execute("now", ADMIN)
        self.radio.advert_result = event(EventType.ERROR, {"reason": "busy"})
        with self.assertRaisesRegex(CommandError, "^advert: the radio refused the advert; try again$"):
            await self.cmd.execute("", ADMIN)
        self.assertIn("Advert failed (advert from Admin)", self.out.getvalue())

    async def test_without_state(self):
        cmd = AdvertCommand(make_context("advert", radio=self.radio))
        self.assertEqual(await cmd.execute("", ADMIN), "advert: sent a flood advert")


if __name__ == "__main__":
    unittest.main()
