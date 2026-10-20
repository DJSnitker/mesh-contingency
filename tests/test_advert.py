import unittest

from meshcore import EventType

from mesh_contingency.commands.advert import AdvertCommand
from mesh_contingency.api import CommandError, Sender
from mesh_contingency.testing import FakeMeshCore, event, make_context

DANA = Sender("Dana", "d0d0d0d0d0d0")


class AdvertCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.radio = FakeMeshCore()
        self.cmd = AdvertCommand(make_context("advert", radio=self.radio))

    async def test_zero_hop_by_default(self):
        result = await self.cmd.execute("", DANA)
        self.assertEqual(self.radio.adverts, [False])
        self.assertEqual(result.reply, "advert: zero-hop sent")

    async def test_flood_case_insensitive(self):
        result = await self.cmd.execute("FLOOD", DANA)
        self.assertEqual(self.radio.adverts, [True])
        self.assertEqual(result.reply, "advert: flood sent")

    async def test_usage(self):
        with self.assertRaisesRegex(CommandError, r"usage: advert \[flood\]"):
            await self.cmd.execute("everywhere", DANA)
        self.assertEqual(self.radio.adverts, [])

    async def test_radio_error(self):
        self.radio.advert_result = event(EventType.ERROR, {"reason": "busy"})
        with self.assertRaisesRegex(RuntimeError, "radio rejected zero-hop advert"):
            await self.cmd.execute("", DANA)


if __name__ == "__main__":
    unittest.main()
