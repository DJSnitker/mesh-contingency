import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from mesh_contingency.api import CONFIRM_SECONDS, MAX_PARTS, MAX_REPLY_LEN, CommandError, Sender
from mesh_contingency.commands.mailbox import MsgCommand, SetPassCommand
from mesh_contingency.commands.users import (
    LeaveCommand,
    RemoveCommand,
    RenameCommand,
    ResetPassCommand,
    UsersCommand,
    WhoAmICommand,
    WhoisCommand,
    pack,
)
from mesh_contingency.directory import Directory
from mesh_contingency.state import State
from mesh_contingency.testing import make_context

ADMIN = Sender("admin-node", "ad" * 32)
ALICE = Sender("alice-node", "a1" * 32)
BOB = Sender("bob-node", "b0" * 32)

USERS = f"""# the users
[admin]
keys = ["{ADMIN.public_key}"]

[users.{ADMIN.public_key}]
name = "Admin"

[users.{ALICE.public_key}]
name = "Alice"
quickim = "alice@example.com"

# Bob joined later
[users.{BOB.public_key}]
name = "Bob"
"""


class UsersTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.folder / "users.toml"
        self.path.write_text(USERS)
        self.directory = Directory(path=self.path)
        self.directory.load()
        self.clock = 1_000.0
        self.enterContext(mock.patch("mesh_contingency.api.time.monotonic", lambda: self.clock))
        self.sent = []
        state = State(self.folder)
        commands = {}

        def make(cls, name):
            commands[name] = cls(make_context(name, directory=self.directory, state=state, sent=self.sent,
                                              commands=commands))
            return commands[name]

        self.msg, self.setpass = make(MsgCommand, "msg"), make(SetPassCommand, "setpass")
        self.users, self.whois, self.remove, self.rename, self.resetpass, self.whoami, self.leave = (
            make(cls, name) for cls, name in [
                (UsersCommand, "users"), (WhoisCommand, "whois"), (RemoveCommand, "remove"),
                (RenameCommand, "rename"), (ResetPassCommand, "resetpass"), (WhoAmICommand, "whoami"),
                (LeaveCommand, "leave")])

    def in_file(self):
        return tomllib.loads(self.path.read_text())["users"]

    async def test_users(self):
        await self.setpass.execute("blue-canoe-42x", BOB)
        self.assertEqual((await self.users.execute("", ADMIN)).reply,
                         ["users (3): Admin adadadadadad (admin) Alice a1a1a1a1a1a1 (quickim) "
                          "Bob b0b0b0b0b0b0 (pass)"])

    async def test_users_pages(self):
        for i in range(40):
            self.directory.save_user(f"{i:02d}" * 32, {"name": f"Person {i:02d}"})
        first = (await self.users.execute("", ADMIN)).reply
        self.assertEqual(len(first), MAX_PARTS)
        self.assertTrue(all(len(m) <= MAX_REPLY_LEN for m in first))
        self.assertEqual(first[-1], "users: page 1 of 2; send users 2 for more")
        self.assertIn("Person 39", " ".join((await self.users.execute("2", ADMIN)).reply))
        with self.assertRaisesRegex(CommandError, r"^users: there are 2 page\(s\)$"):
            await self.users.execute("3", ADMIN)

    async def test_whois_and_whoami(self):
        await self.msg.execute("Alice hello", BOB)
        expected = "Alice (a1a1a1a1a1a1); no passphrase; quickim alice@example.com; 1 message(s), 1 unread"
        self.assertEqual((await self.whois.execute("alice", ADMIN)).reply, expected)
        self.assertEqual((await self.whois.execute("a1a1", ADMIN)).reply, expected)
        self.assertEqual((await self.whoami.execute("", ALICE)).reply, expected)
        self.assertEqual((await self.whoami.execute("", ADMIN)).reply,
                         "Admin (adadadadadad); admin; no passphrase; no messages")
        self.directory.save_user(BOB.public_key, {"name": "Bob", "emailall": ["a@x.org", "b@x.org", "c@x.org"]})
        self.assertEqual((await self.whoami.execute("", BOB)).reply,
                         "Bob (b0b0b0b0b0b0); no passphrase; emailall 3 address(es); no messages")
        with self.assertRaisesRegex(CommandError, "^whois: no user Carol$"):
            await self.whois.execute("Carol", ADMIN)
        with self.assertRaisesRegex(CommandError, "^usage: whois <name or key>$"):
            await self.whois.execute("", ADMIN)

    async def test_remove_asks_first(self):
        await self.msg.execute("Bob hi", ALICE)
        self.assertEqual((await self.remove.execute("bob", ADMIN)).reply,
                         "remove: this removes Bob (b0b0b0b0b0b0) and their 1 message(s). Send it again within "
                         "5 min to confirm.")
        self.assertIn(BOB.public_key, self.directory.users)
        self.assertEqual((await self.remove.execute("bob", ADMIN)).reply, "remove: Bob removed, 1 message(s) deleted")
        self.assertNotIn(BOB.public_key, self.directory.users)
        self.assertNotIn(BOB.public_key, self.in_file())
        self.assertIn("# the users", self.path.read_text())  # the rest of the file kept
        self.assertNotIn(BOB.public_key, self.msg.boxes)

    async def test_remove_confirmation_expires_or_changes(self):
        await self.remove.execute("bob", ADMIN)
        self.clock += CONFIRM_SECONDS
        self.assertIn("Send it again", (await self.remove.execute("bob", ADMIN)).reply)
        await self.remove.execute("alice", ADMIN)  # something else starts over
        self.assertIn("Send it again", (await self.remove.execute("bob", ADMIN)).reply)
        self.assertIn(BOB.public_key, self.directory.users)

    async def test_removing_an_admin_keeps_admin_rights(self):
        await self.remove.execute("admin", ADMIN)
        self.assertEqual((await self.remove.execute("admin", ADMIN)).reply,
                         "remove: Admin removed, 0 message(s) deleted; still an admin (edit [admin] keys to change "
                         "that)")
        self.assertIn(ADMIN.public_key, self.directory.admins)

    async def test_rename(self):
        self.assertEqual((await self.rename.execute("alice Alice Smith", ADMIN)).reply,
                         "rename: Alice is now Alice Smith")
        self.assertEqual(self.in_file()[ALICE.public_key], {"name": "Alice Smith", "quickim": "alice@example.com"})
        self.assertEqual((await self.rename.execute("Alice Smith   Al", ADMIN)).reply, "rename: Alice Smith is now Al")
        with self.assertRaisesRegex(CommandError, "^rename: bob is already b0b0b0b0b0b0's name$"):
            await self.rename.execute("Al bob", ADMIN)
        with self.assertRaisesRegex(CommandError, "^rename: name must be up to 32 plain characters$"):
            await self.rename.execute("Al " + "x" * 33, ADMIN)
        with self.assertRaisesRegex(CommandError, r"^usage: rename <name or key> <new name>$"):
            await self.rename.execute("Al", ADMIN)

    async def test_resetpass(self):
        await self.setpass.execute("blue-canoe-42x", ALICE)
        await self.msg.execute("Alice sealed", BOB)
        self.assertIn("deletes 1 sealed message(s)", (await self.resetpass.execute("alice", ADMIN)).reply)
        self.assertEqual((await self.resetpass.execute("alice", ADMIN)).reply,
                         "resetpass: Alice's passphrase cleared, 1 sealed message(s) deleted")
        self.assertNotIn("inbox_key", self.in_file()[ALICE.public_key])
        self.assertEqual(self.in_file()[ALICE.public_key]["quickim"], "alice@example.com")
        self.assertEqual(self.sent[-1], (ALICE.public_key, "An admin cleared your passphrase; 1 sealed message(s) "
                                                           "deleted. New messages are kept unsealed until you send "
                                                           "setpass."))
        with self.assertRaisesRegex(CommandError, "^resetpass: Alice has no passphrase$"):
            await self.resetpass.execute("alice", ADMIN)

    async def test_resetpass_without_sealed_messages_needs_no_confirming(self):
        self.directory.save_user(BOB.public_key, {"name": "Chris", "inbox_key": {"public": "00"}})
        self.assertEqual((await self.resetpass.execute("chris", ADMIN)).reply,
                         "resetpass: Chris' passphrase cleared, 0 sealed message(s) deleted")
        self.assertEqual(self.sent[-1], (BOB.public_key, "An admin cleared your passphrase. New messages are kept "
                                                         "unsealed until you send setpass."))

    async def test_leave(self):
        await self.msg.execute("Bob hi", ALICE)
        self.assertIn("deletes your 1 message(s)", (await self.leave.execute("", BOB)).reply)
        self.assertEqual((await self.leave.execute("", BOB)).reply,
                         "leave: you're no longer a user; send join to ask again.")
        self.assertNotIn(BOB.public_key, self.in_file())
        self.assertNotIn(BOB.public_key, self.msg.boxes)
        await self.leave.execute("", ADMIN)
        self.assertIn("You're still an admin.", (await self.leave.execute("", ADMIN)).reply)

    async def test_confirmations_are_per_person(self):
        await self.leave.execute("", BOB)
        self.assertIn("Send it again", (await self.leave.execute("", ALICE)).reply)
        self.assertIn("no longer a user", (await self.leave.execute("", BOB)).reply)


class PackTest(unittest.TestCase):
    def test_pack(self):
        self.assertEqual(pack(["a", "b", "c"], limit=5), ["a; b", "c"])
        self.assertEqual(pack(["x" * 10], limit=5), ["xx..."])
        self.assertEqual(pack([]), [])


if __name__ == "__main__":
    unittest.main()
