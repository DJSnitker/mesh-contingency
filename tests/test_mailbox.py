import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mesh_contingency.api import MAX_PARTS, MAX_REPLY_LEN, CommandError, Sender
from mesh_contingency.commands.mailbox import MAX_WAITING, ClearInboxCommand, InboxCommand, MsgCommand
from mesh_contingency.state import State
from mesh_contingency.testing import make_context

ALICE = Sender("alice-node", "a1" * 32)
ANN_LEE = Sender("ann", "a2" * 32)
ANN = Sender("ann2", "a3" * 32)
NONAME = Sender("n0", "c0" * 32)
USERS = {ALICE.public_key: {"name": "Alice"}, ANN_LEE.public_key: {"name": "Ann Lee"},
         ANN.public_key: {"name": "Ann"}, NONAME.public_key: {}}


class MailboxTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.now = 50_000.0
        self.enterContext(mock.patch("mesh_contingency.commands.mailbox.time.time", lambda: self.now))
        self.enterContext(mock.patch("mesh_contingency.state.time.time", lambda: self.now))
        self.start()

    def start(self):
        """Start (or restart) the commands with the mailbox in self.folder."""
        state = State(self.folder)
        self.msg = MsgCommand(make_context("msg", users=USERS, state=state))
        self.inbox = InboxCommand(make_context("inbox", users=USERS, state=state))
        self.clear = ClearInboxCommand(make_context("clearinbox", users=USERS, state=state))

    async def test_leave_read_and_clear_a_message(self):
        result = await self.msg.execute("alice are you safe?", ANN)
        self.assertEqual(result.reply, "msg: saved for Alice (1 in their inbox)")
        self.now += 600
        self.assertEqual((await self.inbox.execute("", ALICE)).reply, ["Ann 10m ago: are you safe?"])
        self.assertEqual((await self.inbox.execute("", ALICE)).reply, ["Ann 10m ago: are you safe?"])  # kept
        self.assertEqual((await self.clear.execute("", ALICE)).reply, "clearinbox: deleted 1 message(s)")
        self.assertEqual((await self.inbox.execute("", ALICE)).reply, "inbox: no messages")

    async def test_kept_across_restarts_until_cleared(self):
        await self.msg.execute("Alice first", ANN)
        await self.msg.execute("Alice second", ANN_LEE)
        self.start()  # the bot restarts
        self.assertEqual((await self.inbox.execute("", ALICE)).reply,
                         ["Ann just now: first", "Ann Lee just now: second"])
        self.start()
        self.assertEqual(len((await self.inbox.execute("", ALICE)).reply), 2)  # still there
        await self.clear.execute("", ALICE)
        self.assertEqual(json.loads((self.folder / "mailbox.json").read_text()), {})
        self.start()
        self.assertEqual((await self.inbox.execute("", ALICE)).reply, "inbox: no messages")

    async def test_clear_keeps_messages_not_yet_shown(self):
        await self.msg.execute("Alice seen", ANN)
        await self.inbox.execute("", ALICE)
        await self.msg.execute("Alice arrived since", ANN)
        self.assertEqual((await self.clear.execute("", ALICE)).reply,
                         "clearinbox: deleted 1 message(s); 1 new one(s) kept, see inbox")
        self.assertEqual((await self.inbox.execute("", ALICE)).reply, ["Ann just now: arrived since"])
        self.assertEqual((await self.clear.execute("", ALICE)).reply, "clearinbox: deleted 1 message(s)")
        self.assertEqual((await self.clear.execute("", ALICE)).reply, "clearinbox: deleted 0 message(s)")
        with self.assertRaisesRegex(CommandError, "^usage: clearinbox$"):
            await self.clear.execute("all", ALICE)

    async def test_longest_matching_name_wins(self):
        await self.msg.execute("ann lee hello", ALICE)
        await self.msg.execute("ANN hi", ALICE)
        self.assertEqual((await self.inbox.execute("", ANN_LEE)).reply, ["Alice just now: hello"])
        self.assertEqual((await self.inbox.execute("", ANN)).reply, ["Alice just now: hi"])

    async def test_name_must_be_a_whole_word(self):
        with self.assertRaisesRegex(CommandError, "^msg: no user Annie$"):
            await self.msg.execute("Annie hello", ALICE)

    async def test_by_key_prefix(self):
        self.assertEqual((await self.msg.execute("C0C0 hello", ALICE)).reply,
                         "msg: saved for c0c0c0c0c0c0 (1 in their inbox)")
        with self.assertRaisesRegex(CommandError, "no user a"):
            await self.msg.execute("a hello", ALICE)  # too short
        with self.assertRaisesRegex(CommandError, "no user a1a"):
            await self.msg.execute("a1a hello", ALICE)

    async def test_only_users_can_be_written_to(self):
        with self.assertRaisesRegex(CommandError, "^msg: no user Bob$"):
            await self.msg.execute("Bob hello", ALICE)

    async def test_usage(self):
        for text in ("", "Alice", "Alice   "):
            with self.subTest(text=text), self.assertRaisesRegex(CommandError, r"^usage: msg <name> <message>$"):
                await self.msg.execute(text, ANN)
        with self.assertRaisesRegex(CommandError, r"^usage: inbox \[page\]$"):
            await self.inbox.execute("all", ALICE)

    async def test_full_inbox(self):
        for i in range(MAX_WAITING):
            await self.msg.execute(f"Alice {i}", ANN)
        with self.assertRaisesRegex(CommandError, "^msg: Alice's inbox is full$"):
            await self.msg.execute("Alice one more", ANN)

    async def test_many_messages_come_in_pages(self):
        for i in range(10):
            await self.msg.execute(f"Alice message {i}", ANN)
        first = (await self.inbox.execute("", ALICE)).reply
        self.assertEqual(len(first), MAX_PARTS)
        self.assertEqual(first[-1], "inbox: page 1 of 2; send inbox 2 for more")
        self.assertEqual((await self.inbox.execute("1", ALICE)).reply, first)
        second = (await self.inbox.execute("2", ALICE)).reply
        self.assertEqual(second, [f"Ann just now: message {i}" for i in (7, 8, 9)])
        with self.assertRaisesRegex(CommandError, r"^inbox: there are 2 page\(s\)$"):
            await self.inbox.execute("3", ALICE)

    async def test_clear_after_the_first_page_keeps_the_rest(self):
        for i in range(10):
            await self.msg.execute(f"Alice message {i}", ANN)
        await self.inbox.execute("", ALICE)
        self.assertEqual((await self.clear.execute("", ALICE)).reply,
                         "clearinbox: deleted 7 message(s); 3 new one(s) kept, see inbox")
        self.assertEqual(len((await self.inbox.execute("", ALICE)).reply), 3)

    async def test_full_until_cleared(self):
        for i in range(MAX_WAITING):
            await self.msg.execute(f"Alice {i}", ANN)
        for page in ("1", "2", "3"):
            await self.inbox.execute(page, ALICE)
        await self.clear.execute("", ALICE)
        self.assertEqual((await self.msg.execute("Alice room again", ANN)).reply,
                         "msg: saved for Alice (1 in their inbox)")

    async def test_long_message_is_split(self):
        text = "word " * 40
        await self.msg.execute(f"Alice {text}", ANN)
        reply = (await self.inbox.execute("", ALICE)).reply
        self.assertEqual(len(reply), 2)
        self.assertTrue(reply[0].startswith("(1/2) Ann just now: word"))
        self.assertTrue(all(len(part) <= MAX_REPLY_LEN for part in reply))

    async def test_each_reader_gets_only_their_own(self):
        await self.msg.execute("Alice for alice", ANN)
        self.assertEqual((await self.inbox.execute("", ANN)).reply, "inbox: no messages")
        self.assertEqual((await self.inbox.execute("", ALICE)).reply, ["Ann just now: for alice"])


if __name__ == "__main__":
    unittest.main()
