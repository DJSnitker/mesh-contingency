import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mesh_contingency.api import CommandError, Sender
from mesh_contingency.commands.status import ClearStatusCommand, OkCommand, StatusCommand
from mesh_contingency.state import State, StoreError
from mesh_contingency.testing import make_context

ALICE = Sender("alice-t1000", "a1" * 32)
BOB = Sender("Bob", "b0" * 32)
OTHER_BOB = Sender("Bob", "b1" * 32)
NOBODY = Sender("ffeeddccbbaa", None)  # not identified
USERS = {ALICE.public_key: {"name": "Alice"}}


class StatusTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.state = State(self.folder)
        self.now = 10_000.0
        self.enterContext(mock.patch("mesh_contingency.commands.status.time.time", lambda: self.now))
        self.enterContext(mock.patch("mesh_contingency.state.time.time", lambda: self.now))
        self.ok, self.status, self.clear = (cls(make_context(name, users=USERS, state=self.state)) for cls, name in
                                            [(OkCommand, "ok"), (StatusCommand, "status"),
                                             (ClearStatusCommand, "clearstatus")])

    async def test_ok_and_status(self):
        result = await self.ok.execute("at home, all fine", BOB)
        self.assertEqual(result.reply, "ok: saved for Bob")
        self.now += 2 * 3600
        self.assertEqual((await self.status.execute("bob", ALICE)).reply, "Bob: at home, all fine (2h ago)")

    async def test_plain_ok(self):
        await self.ok.execute("", BOB)
        self.assertEqual((await self.status.execute("Bob", BOB)).reply, "Bob: ok (just now)")

    async def test_latest_status_replaces_the_last(self):
        await self.ok.execute("leaving", BOB)
        await self.ok.execute("arrived", BOB)
        self.assertEqual((await self.status.execute("Bob", ALICE)).reply, "Bob: arrived (just now)")

    async def test_users_file_name_is_used(self):
        self.assertEqual((await self.ok.execute("", ALICE)).reply, "ok: saved for Alice")
        self.assertEqual((await self.status.execute("alice", BOB)).reply, "Alice: ok (just now)")

    async def test_lookup_by_part_of_name_or_key(self):
        await self.ok.execute("", ALICE)
        await self.ok.execute("", BOB)
        self.assertEqual((await self.status.execute("lic", BOB)).reply, "Alice: ok (just now)")
        self.assertEqual((await self.status.execute("B0B0", BOB)).reply, "Bob: ok (just now)")
        self.assertEqual((await self.status.execute(ALICE.public_key, BOB)).reply, "Alice: ok (just now)")

    async def test_same_name_shows_both_with_key_prefixes(self):
        await self.ok.execute("home", BOB)
        self.now += 60
        await self.ok.execute("away", OTHER_BOB)
        self.assertEqual((await self.status.execute("bob", ALICE)).reply,
                         "Bob (b1b1b1b1b1b1): away (just now); Bob (b0b0b0b0b0b0): home (1m ago)")

    async def test_exact_name_beats_partial(self):
        await self.ok.execute("", BOB)
        await self.ok.execute("", Sender("Bobby", "b2" * 32))
        self.assertEqual((await self.status.execute("bob", ALICE)).reply, "Bob: ok (just now)")

    async def test_radio_name_with_spaces_plain_or_in_brackets(self):
        await self.ok.execute("at the shelter", Sender("Ridge Base 1", "b3" * 32))
        for text in ["ridge base 1", "(Ridge Base 1)", "Ridge"]:
            self.assertEqual((await self.status.execute(text, ALICE)).reply, "Ridge Base 1: at the shelter (just now)")

    async def test_no_status(self):
        with self.assertRaisesRegex(CommandError, "^status: no status for carol$"):
            await self.status.execute("carol", BOB)

    async def test_no_argument_shows_your_own(self):
        with self.assertRaisesRegex(CommandError, r"^usage: status <name or key>$"):
            await self.status.execute("", BOB)
        await self.ok.execute("fine", BOB)
        self.assertEqual((await self.status.execute("", BOB)).reply, "Bob: fine (just now)")

    async def test_unidentified_sender_cannot_check_in(self):
        with self.assertRaisesRegex(CommandError, "can't tell who you are"):
            await self.ok.execute("", NOBODY)

    async def test_full_key_never_in_replies(self):
        result = await self.ok.execute("", BOB)
        self.assertNotIn(BOB.public_key, result.reply + result.console)

    async def test_kept_across_restarts(self):
        await self.ok.execute("safe", BOB)
        restarted = StatusCommand(make_context("status", state=State(self.folder)))
        self.assertEqual((await restarted.execute("bob", ALICE)).reply, "Bob: safe (just now)")

    async def test_clearstatus(self):
        await self.ok.execute("", BOB)
        await self.ok.execute("", ALICE)
        self.assertEqual((await self.clear.execute("", ALICE)).reply, "clearstatus: cleared 2 statuses")
        with self.assertRaises(CommandError):
            await self.status.execute("bob", ALICE)
        self.assertEqual(State(self.folder).store("status.json").data, {})  # cleared on disk too
        self.assertEqual((await self.clear.execute("", ALICE)).reply, "clearstatus: cleared 0 statuses")
        with self.assertRaisesRegex(CommandError, "^usage: clearstatus$"):
            await self.clear.execute("all", ALICE)

    def test_unreadable_file_stops_the_command_starting(self):
        (self.folder / "other").mkdir()
        (self.folder / "other" / "status.json").write_text("{oops")
        with self.assertRaises(StoreError):
            OkCommand(make_context("ok", state=State(self.folder / "other")))


if __name__ == "__main__":
    unittest.main()
