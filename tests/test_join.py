import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from mesh_contingency.api import CommandError, Sender
from mesh_contingency.commands.join import MAX_REQUESTS, ApproveCommand, DenyCommand, JoinCommand
from mesh_contingency.directory import Directory
from mesh_contingency.state import State
from mesh_contingency.testing import make_context

ADMIN = Sender("Admin", "ad" * 32)
ADMIN2 = "ae" * 32
BOB = Sender("BobNode", "b0" * 32)
CAROL = Sender("Carol", "c0" * 32)
DANA = Sender("Dana", "d0" * 32)  # already a user


class JoinTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = folder / "users.toml"
        self.path.write_text(f'[admin]\nkeys = ["{ADMIN.public_key}", "{ADMIN2}"]\n\n'
                             f'[users.{DANA.public_key}]\nname = "Dana"\n')
        self.directory = Directory(path=self.path)
        self.directory.load()
        self.sent = []
        state = State(folder)
        self.join, self.approve, self.deny = (
            cls(make_context(name, directory=self.directory, state=state, sent=self.sent))
            for cls, name in [(JoinCommand, "join"), (ApproveCommand, "approve"), (DenyCommand, "deny")])

    async def test_join_tells_the_admins(self):
        result = await self.join.execute("BobSmith", BOB)
        self.assertEqual(result.reply, "join: request sent to the admins")
        notice = "Join request: BobSmith (b0b0b0b0b0b0). Reply approve b0b0b0b0b0b0 or deny b0b0b0b0b0b0"
        self.assertEqual(self.sent, [(ADMIN.public_key, notice), (ADMIN2, notice)])

    async def test_name_must_be_letters_and_numbers(self):
        for name in ["Bob Smith", "Bob-Smith", "José", "x" * 33]:
            with self.assertRaisesRegex(CommandError, "^join: name must be one word of letters and numbers, up to 32, "
                                                      "e.g. SamJones$"):
                await self.join.execute(name, BOB)
        self.assertEqual(self.sent, [])

    async def test_profane_names_are_refused(self):
        for name in ["BigAss", "5h1t", "Fuckface"]:
            with self.assertRaisesRegex(CommandError, "^join: that name isn't allowed; choose another$"):
                await self.join.execute(name, BOB)
        self.assertEqual(self.sent, [])

    async def test_a_radio_name_is_kept_to_one_word(self):
        result = await self.join.execute("", replace(BOB, name="Bob T-1000"))
        self.assertEqual(result.reply,
                         "join: request sent to the admins as BobT1000; send join <name> to choose another")
        self.assertEqual(self.sent[0], (ADMIN.public_key, "Join request: BobT1000 (b0b0b0b0b0b0). "
                                                          "Reply approve b0b0b0b0b0b0 or deny b0b0b0b0b0b0"))
        self.assertEqual((await self.join.execute("Bob", BOB)).reply, "join: request updated")
        self.assertIn("Bob (b0b0b0b0b0b0)", (await self.approve.execute("", ADMIN)).reply)

    async def test_a_radio_name_that_cant_be_used_needs_a_name(self):
        for radio in ["\U0001f525", "Big Ass"]:
            with self.assertRaisesRegex(CommandError, "^join: your radio's name can't be used; send join <name>$"):
                await self.join.execute("", replace(BOB, name=radio))
        self.assertEqual(self.sent, [])

    async def test_asking_again_updates_without_telling_the_admins_again(self):
        await self.join.execute("", BOB)
        self.sent.clear()
        self.assertEqual((await self.join.execute("Robert", BOB)).reply, "join: request updated")
        self.assertEqual(self.sent, [])
        self.assertIn("Robert (b0b0b0b0b0b0)", (await self.approve.execute("", ADMIN)).reply)

    async def test_approve_writes_the_users_file(self):
        await self.join.execute("", BOB)  # the node's name
        self.sent.clear()
        result = await self.approve.execute("BOBNODE", ADMIN)
        self.assertEqual(result.reply, "approve: BobNode added to users.toml")
        self.assertEqual(self.directory.users[BOB.public_key], {"name": "BobNode"})
        self.assertIn(f'[users.{BOB.public_key}]\nname = "BobNode"\n', self.path.read_text())
        self.assertEqual(self.sent, [(BOB.public_key,
                                      "Welcome, BobNode: you're now a user. Send help for your commands.")])
        self.assertEqual((await self.approve.execute("", ADMIN)).reply, "approve: no requests")

    async def test_list_and_choose_by_key_prefix(self):
        await self.join.execute("Bob", BOB)
        await self.join.execute("Bob", CAROL)
        self.assertRegex((await self.approve.execute("", ADMIN)).reply,
                         r"^requests: Bob \(b0b0b0b0b0b0\) just now; Bob \(c0c0c0c0c0c0\) just now$")
        with self.assertRaisesRegex(CommandError, "2 requests match; use the key prefix: b0b0b0b0b0b0, c0c0c0c0c0c0"):
            await self.approve.execute("bob", ADMIN)
        await self.approve.execute("C0C0", ADMIN)
        self.assertEqual(self.directory.users[CAROL.public_key], {"name": "Bob"})
        self.assertNotIn(BOB.public_key, self.directory.users)

    async def test_deny(self):
        await self.join.execute("", BOB)
        self.sent.clear()
        self.assertEqual((await self.deny.execute("b0b0", ADMIN)).reply, "deny: request from BobNode removed")
        self.assertEqual(self.sent, [])  # not told
        self.assertNotIn(BOB.public_key, self.directory.users)
        with self.assertRaisesRegex(CommandError, "^deny: no request from b0b0$"):
            await self.deny.execute("b0b0", ADMIN)
        with self.assertRaisesRegex(CommandError, r"^usage: deny <name or key>$"):
            await self.deny.execute("", ADMIN)

    async def test_requests_survive_a_restart(self):
        await self.join.execute("", BOB)
        restarted = ApproveCommand(make_context("approve", directory=self.directory,
                                                state=State(self.path.parent)))
        await restarted.execute("BobNode", ADMIN)
        self.assertIn(BOB.public_key, self.directory.users)

    async def test_refusals(self):
        with self.assertRaisesRegex(CommandError, "already a user"):
            await self.join.execute("", DANA)
        with self.assertRaisesRegex(CommandError, "can't tell who you are"):
            await self.join.execute("", Sender("ffeeddccbbaa", None))
        for name in ("x" * 33, "two\x00parts"):
            with self.subTest(name=name), self.assertRaisesRegex(CommandError, "name must be"):
                await self.join.execute(name, BOB)
        with self.assertRaisesRegex(CommandError, "^approve: no request from Zed$"):
            await self.approve.execute("Zed", ADMIN)

    async def test_too_many_requests(self):
        for i in range(MAX_REQUESTS):
            await self.join.execute("", Sender(f"n{i}", f"{i:02x}" * 32))
        with self.assertRaisesRegex(CommandError, "too many requests waiting"):
            await self.join.execute("", BOB)

    async def test_names_that_could_break_the_file_are_refused(self):
        for name in ['Bob"]\n[admin]', 'Bob"][admin]x=1']:
            with self.assertRaisesRegex(CommandError, "letters and numbers"):
                await self.join.execute(name, BOB)
        self.assertEqual((await self.approve.execute("", ADMIN)).reply, "approve: no requests")
        self.assertEqual(self.directory.admins, {ADMIN.public_key, ADMIN2})

    async def test_user_added_by_hand_meanwhile(self):
        await self.join.execute("", BOB)
        self.path.write_text(self.path.read_text() + f'[users.{BOB.public_key}]\nname = "Bobby"\n')
        self.directory.check(force=True)
        await self.approve.execute("b0b0", ADMIN)
        self.assertEqual(self.directory.users[BOB.public_key], {"name": "Bobby"})  # not overwritten

    async def test_users_file_problem(self):
        await self.join.execute("", BOB)
        self.path.write_text("[users")
        with self.assertRaisesRegex(CommandError, "^approve: users.toml not valid TOML"):
            await self.approve.execute("b0b0", ADMIN)
        self.assertIn("BobNode", (await self.approve.execute("", ADMIN)).reply)  # still waiting


if __name__ == "__main__":
    unittest.main()
