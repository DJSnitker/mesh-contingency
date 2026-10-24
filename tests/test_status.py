import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mesh_contingency.api import CommandError, Sender
from mesh_contingency.commands.status import CheckinsCommand, ClearStatusCommand, OkCommand, StatusCommand
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


class CheckinsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.state = State(self.folder)
        self.now = 10_000.0
        self.enterContext(mock.patch("mesh_contingency.commands.status.time.time", lambda: self.now))
        self.enterContext(mock.patch("mesh_contingency.state.time.time", lambda: self.now))
        # Create users with multiple people
        self.users = {
            ALICE.public_key: {"name": "Alice"},
            BOB.public_key: {"name": "Bob"},
            OTHER_BOB.public_key: {"name": "Bobby"},
            "c3" * 32: {"name": "Charlie"},
            "d4" * 32: {"name": "David"},
        }
        self.checkins = CheckinsCommand(make_context("checkins", users=self.users, state=self.state))
        self.ok = OkCommand(make_context("ok", users=self.users, state=self.state))

    async def test_checkins_shows_all_users(self):
        # No check-ins yet, everyone should be missing
        result = await self.checkins.execute("", ALICE)
        self.assertIn("Alice: missing", result.reply)
        self.assertIn("Bob: missing", result.reply)
        self.assertIn("Bobby: missing", result.reply)
        self.assertIn("Charlie: missing", result.reply)
        self.assertIn("David: missing", result.reply)
        self.assertIn("0/5 checked in", result.reply)

    async def test_checkins_shows_checked_in_users(self):
        # Alice and Bob check in
        await self.ok.execute("standing by", ALICE)
        await self.ok.execute("at home", BOB)
        result = await self.checkins.execute("", ALICE)
        self.assertIn("Alice: standing by", result.reply)
        self.assertIn("Bob: at home", result.reply)
        self.assertIn("Bobby: missing", result.reply)
        self.assertIn("2/5 checked in", result.reply)

    async def test_checkins_shows_timestamps(self):
        await self.ok.execute("ready", ALICE)
        self.now += 5 * 60  # 5 minutes later
        result = await self.checkins.execute("", BOB)
        self.assertIn("Alice: ready (5m ago)", result.reply)

    def six_users(self):
        """A checkins command over six users: two pages of five and one."""
        users = {**self.users, "f6" * 32: {"name": "Frank"}}
        return CheckinsCommand(make_context("checkins", users=users, state=self.state))

    async def test_checkins_pagination_default_page_one(self):
        result = await self.six_users().execute("", ALICE)
        self.assertIn("Alice: missing", result.reply)
        self.assertIn("David: missing", result.reply)
        self.assertNotIn("Frank", result.reply)
        self.assertIn("0/6 checked in. Page 1/2.", result.reply)

    async def test_checkins_pagination_page_two(self):
        await self.ok.execute("at the shelter", ALICE)
        result = await self.six_users().execute("page 2", ALICE)
        self.assertIn("Frank: missing", result.reply)
        self.assertNotIn("Alice", result.reply)
        self.assertIn("1/6 checked in. Page 2/2.", result.reply)

    async def test_checkins_invalid_page_number(self):
        await self.ok.execute("", ALICE)
        with self.assertRaisesRegex(CommandError, "page 10 out of range"):
            await self.checkins.execute("page 10", ALICE)

    async def test_checkins_invalid_arguments(self):
        with self.assertRaisesRegex(CommandError, "^usage: checkins"):
            await self.checkins.execute("invalid arg", ALICE)

    async def test_checkins_summary_count_all_users(self):
        # Check in only 2 out of 5 users
        await self.ok.execute("ok", ALICE)
        await self.ok.execute("ok", BOB)
        result = await self.checkins.execute("", ALICE)
        # Summary should show 2/5 total users
        self.assertIn("2/5 checked in", result.reply)

    async def test_checkins_summary_counts_only_users(self):
        # ok is public: a stranger's check-in isn't one of the users'.
        await self.ok.execute("ok", ALICE)
        await self.ok.execute("passing through", Sender("Stranger", "e5" * 32))
        result = await self.checkins.execute("", ALICE)
        self.assertIn("1/5 checked in", result.reply)

    async def test_checkins_pagination_message_shows_navigation(self):
        result = await self.six_users().execute("", ALICE)
        self.assertIn("Use 'checkins page <n>' to see other pages.", result.reply)
        result = await self.checkins.execute("", ALICE)
        self.assertNotIn("checkins page", result.reply)


if __name__ == "__main__":
    unittest.main()
