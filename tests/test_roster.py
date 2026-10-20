import unittest
from unittest import mock

from mesh_contingency.api import CommandError, Sender
from mesh_contingency.commands.roster import RosterCommand
from mesh_contingency.state import State
from mesh_contingency.testing import make_context

DANA = Sender("Dana", "d0" * 32)


class RosterTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = State()
        self.cmd = RosterCommand(make_context("roster", state=self.state))
        self.enterContext(mock.patch("mesh_contingency.commands.roster.time.strftime", return_value="Oct 20 08:47"))

    async def test_most_recent_first(self):
        for key, name in [("a", "Alice"), ("b", "Bob"), ("d", "Dana"), ("a", "Alice")]:
            self.state.saw(key, name)
        result = await self.cmd.execute("", DANA)
        self.assertEqual(result.reply, "roster since Oct 20 08:47 (3): Alice, Dana, Bob")

    async def test_empty(self):
        self.assertEqual((await self.cmd.execute("", DANA)).reply, "roster since Oct 20 08:47 (0)")

    async def test_usage(self):
        with self.assertRaisesRegex(CommandError, "^usage: roster$"):
            await self.cmd.execute("all", DANA)


if __name__ == "__main__":
    unittest.main()
