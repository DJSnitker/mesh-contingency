import tempfile
import tomllib
import unittest
from pathlib import Path

from mesh_contingency.api import CommandError, Sender
from mesh_contingency.commands.settings import MAX_GROUP, AddGroupCommand, ClearGroupCommand, SetQmCommand
from mesh_contingency.directory import Directory
from mesh_contingency.testing import make_context

DANA = Sender("Dana", "d0" * 32)
ERIN = Sender("Erin", "e0" * 32)


class SettingsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = folder / "users.toml"
        self.path.write_text(f'[users.{DANA.public_key}]\nname = "Dana"\nqm = "old@example.com"\n'
                             f'emailall = "one@example.com"\n\n[users.{ERIN.public_key}]\nname = "Erin"\n')
        self.directory = Directory(path=self.path)
        self.directory.load()
        self.setqm, self.addgroup, self.cleargroup = (
            cls(make_context(name, directory=self.directory)) for cls, name in
            [(SetQmCommand, "setqm"), (AddGroupCommand, "addgroup"), (ClearGroupCommand, "cleargroup")])

    def saved(self, sender):
        """The sender's section as now in the file."""
        return tomllib.loads(self.path.read_text())["users"][sender.public_key]

    async def test_setqm(self):
        self.assertEqual((await self.setqm.execute("", DANA)).reply, "qm: old@example.com")
        self.assertEqual((await self.setqm.execute("new@example.com", DANA)).reply,
                         "qm now sends to new@example.com")
        self.assertEqual(self.saved(DANA)["qm"], "new@example.com")
        self.assertEqual(self.directory.users[DANA.public_key]["qm"], "new@example.com")  # used at once
        self.assertEqual(self.saved(ERIN), {"name": "Erin"})  # others untouched
        self.assertEqual((await self.setqm.execute("", ERIN)).reply, "qm: no address set")

    async def test_addgroup_and_cleargroup(self):
        self.assertEqual((await self.addgroup.execute("", DANA)).reply, "emailall: one@example.com")
        self.assertEqual((await self.addgroup.execute("two@example.com", DANA)).reply,
                         "addgroup: two@example.com added (2 in the group)")
        self.assertEqual(self.saved(DANA)["emailall"], ["one@example.com", "two@example.com"])
        with self.assertRaisesRegex(CommandError, "already in the group"):
            await self.addgroup.execute("TWO@example.com", DANA)
        self.assertEqual((await self.cleargroup.execute("", DANA)).reply, "cleargroup: removed 2 address(es)")
        self.assertNotIn("emailall", self.saved(DANA))
        self.assertEqual(self.saved(DANA)["qm"], "old@example.com")
        self.assertEqual((await self.addgroup.execute("", DANA)).reply, "emailall: no addresses")
        self.assertEqual((await self.cleargroup.execute("", DANA)).reply, "cleargroup: removed 0 address(es)")

    async def test_group_limit(self):
        for i in range(MAX_GROUP - 1):
            await self.addgroup.execute(f"p{i}@example.com", DANA)
        with self.assertRaisesRegex(CommandError, "the group is full"):
            await self.addgroup.execute("more@example.com", DANA)

    async def test_only_plain_addresses(self):
        for text in ("not-an-address", "-oQ/tmp/x@example.com", "a@example.com b@example.com", "|cmd@example.com"):
            with self.subTest(text=text), self.assertRaisesRegex(CommandError, "not an email address"):
                await self.setqm.execute(text, DANA)
            with self.subTest(text=text), self.assertRaises(CommandError):
                await self.addgroup.execute(text, DANA)
        self.assertEqual(self.saved(DANA)["qm"], "old@example.com")

    async def test_usage(self):
        with self.assertRaisesRegex(CommandError, "^usage: cleargroup$"):
            await self.cleargroup.execute("all", DANA)

    async def test_setting_for_another_command(self):
        cmd = SetQmCommand(make_context("setfam", options={"command": "quickfam"}, directory=self.directory))
        self.assertEqual((await cmd.execute("fam@example.com", DANA)).reply, "quickfam now sends to fam@example.com")
        self.assertEqual(self.saved(DANA)["quickfam"], "fam@example.com")


if __name__ == "__main__":
    unittest.main()
