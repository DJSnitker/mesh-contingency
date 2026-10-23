import tempfile
import tomllib
import unittest
from pathlib import Path

from mesh_contingency.api import CommandError, Sender
from mesh_contingency.commands.settings import (
    MAX_GROUP,
    AddGroupCommand,
    ClearGroupCommand,
    SetEmailCommand,
    SetQmCommand,
)
from mesh_contingency.directory import Directory
from mesh_contingency.state import HISTORY_FILE, State
from mesh_contingency.testing import make_context

ADMIN = Sender("Admin", "ad" * 32)
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
        self.sent, self.state = [], State()
        self.setemail = SetEmailCommand(make_context("setemail", directory=self.directory, state=self.state,
                                                     sent=self.sent))

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

    async def test_sets_both_and_tells_the_user(self):
        reply = (await self.setemail.execute(f"{DANA.public_key} qm new@example.com group a@example.com "
                                             f"b@example.com A@example.com", ADMIN)).reply
        self.assertEqual(reply, "setemail: Dana's qm new@example.com; emailall a@example.com, b@example.com")
        self.assertEqual(self.saved(DANA), {"name": "Dana", "qm": "new@example.com",
                                            "emailall": ["a@example.com", "b@example.com"]})
        self.assertEqual(self.sent, [(DANA.public_key, "An admin changed your email addresses: qm new@example.com; "
                                                       "emailall a@example.com, b@example.com")])
        what = self.state.store(HISTORY_FILE).data["entries"][-1]["what"]
        self.assertEqual(what, f"set Dana's qm new@example.com; emailall a@example.com, b@example.com "
                               f"({DANA.public_key[:12]})")

    async def test_one_part_alone_and_clearing(self):
        await self.setemail.execute("erin group x@example.com", ADMIN)
        self.assertEqual(self.saved(ERIN), {"name": "Erin", "emailall": ["x@example.com"]})
        self.assertEqual((await self.setemail.execute("Dana qm", ADMIN)).reply, "setemail: Dana's qm cleared")
        self.assertEqual(self.saved(DANA), {"name": "Dana", "emailall": "one@example.com"})

    async def test_refuses(self):
        for text, error in [
            ("", "^usage: "),
            ("nobody qm a@example.com", "no user nobody"),
            ("dana", "^usage: "),
            ("dana a@example.com", "^usage: "),
            ("dana qm a@example.com b@example.com", "qm takes one address"),
            ("dana qm not-an-address", "not an email address: not-an-address"),
            ("dana qm a@example.com qm b@example.com", "qm given twice"),
            ("dana group " + " ".join(f"{i}@example.com" for i in range(MAX_GROUP + 1)), "at most"),
        ]:
            with self.subTest(text), self.assertRaisesRegex(CommandError, error):
                await self.setemail.execute(text, ADMIN)
        self.assertEqual(self.saved(DANA)["qm"], "old@example.com")
        self.assertEqual(self.sent, [])
