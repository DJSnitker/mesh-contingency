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
        result = await self.join.execute("", BOB)
        self.assertEqual(result.reply, "join: request sent to the admins as BobNode")
        notice = "Join request: BobNode (b0b0b0b0b0b0). Reply approve b0b0b0b0b0b0 or deny b0b0b0b0b0b0"
        self.assertEqual(self.sent, [(ADMIN.public_key, notice), (ADMIN2, notice)])

    async def test_the_radios_name_is_used_as_it_is(self):
        result = await self.join.execute("", replace(BOB, name="Ridge Base 1"))
        self.assertEqual(result.reply, "join: request sent to the admins as Ridge Base 1")
        self.assertEqual(self.sent[0], (ADMIN.public_key, "Join request: Ridge Base 1 (b0b0b0b0b0b0). "
                                                          "Reply approve b0b0b0b0b0b0 or deny b0b0b0b0b0b0"))
        self.assertIn("Ridge Base 1 (b0b0b0b0b0b0)", (await self.approve.execute("", ADMIN)).reply)

    async def test_a_name_given_to_join_is_ignored(self):
        result = await self.join.execute("BobSmith", BOB)
        self.assertEqual(result.reply,
                         "join: request sent to the admins as BobNode; you're listed under your radio's name, "
                         "not BobSmith")
        self.assertIn("BobNode (b0b0b0b0b0b0)", (await self.approve.execute("", ADMIN)).reply)

    async def test_radio_names_that_cant_be_used(self):
        for radio, problem in [("Big Ass", "isn't allowed"), ("5h1t", "isn't allowed"),
                               ("Bob\x1b[2J", "control characters"), ("Bob (base)", r"\( or \)"),
                               ("b0b0b0b0b0b0", "has no name")]:  # no name: known by its key prefix
            with self.subTest(radio=radio), self.assertRaisesRegex(CommandError, f"^join: your radio.*{problem}"):
                await self.join.execute("", replace(BOB, name=radio))
        self.assertEqual(self.sent, [])

    async def test_asking_again_updates_without_telling_the_admins_again(self):
        await self.join.execute("", BOB)
        self.sent.clear()
        reply = (await self.join.execute("", replace(BOB, name="Robert T-Deck"))).reply
        self.assertEqual(reply, "join: request updated as Robert T-Deck")
        self.assertEqual(self.sent, [])
        self.assertIn("Robert T-Deck (b0b0b0b0b0b0)", (await self.approve.execute("", ADMIN)).reply)

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

    async def test_approve_by_name_with_spaces(self):
        await self.join.execute("", replace(BOB, name="Ridge Base 1"))
        await self.approve.execute("ridge base 1", ADMIN)
        self.assertEqual(self.directory.users[BOB.public_key], {"name": "Ridge Base 1"})
        await self.join.execute("", replace(CAROL, name="Base #2"))
        await self.approve.execute("(Base #2)", ADMIN)
        self.assertEqual(self.directory.users[CAROL.public_key], {"name": "Base #2"})

    async def test_list_and_choose_by_key_prefix(self):
        await self.join.execute("", replace(BOB, name="Bob"))
        await self.join.execute("", replace(CAROL, name="Bob"))
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
        with self.assertRaisesRegex(CommandError, "^approve: no request from Zed$"):
            await self.approve.execute("Zed", ADMIN)

    async def test_too_many_requests(self):
        for i in range(MAX_REQUESTS):
            await self.join.execute("", Sender(f"n{i}", f"{i:02x}" * 32))
        with self.assertRaisesRegex(CommandError, "too many requests waiting"):
            await self.join.execute("", BOB)

    async def test_names_that_could_break_the_file_are_refused(self):
        with self.assertRaisesRegex(CommandError, "control characters"):
            await self.join.execute("", replace(BOB, name='Bob"]\n[admin]'))
        # Quotes and brackets are written safely, as TOML text.
        await self.join.execute("", replace(BOB, name='Bob"][admin]x=1'))
        await self.approve.execute("b0b0", ADMIN)
        self.assertEqual(self.directory.users[BOB.public_key], {"name": 'Bob"][admin]x=1'})
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
