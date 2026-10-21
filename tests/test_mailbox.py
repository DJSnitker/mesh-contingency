import json
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from mesh_contingency.api import MAX_PARTS, MAX_REPLY_LEN, CommandError, Sender
from mesh_contingency.commands.mailbox import (
    CONFIRM_SECONDS,
    MAX_WAITING,
    NOTICE_SECONDS,
    ClearInboxCommand,
    InboxCommand,
    MsgCommand,
    SetPassCommand,
)
from mesh_contingency.directory import Directory
from mesh_contingency.sealing import new_inbox_key
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
        with self.assertRaisesRegex(CommandError, r"^usage: clearinbox \[all\]$"):
            await self.clear.execute("everything", ALICE)

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
        with self.assertRaisesRegex(CommandError, r"^usage: inbox \[passphrase\] \[page\]$"):
            await self.inbox.execute("some long words", ALICE)
        with self.assertRaisesRegex(CommandError, "^inbox: you have no passphrase; send inbox alone$"):
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

    async def test_console_never_shows_the_text(self):
        result = await self.msg.execute("Alice the code is 1234", ANN)
        self.assertEqual(result.console, "Message for Alice from Ann")
        self.assertNotIn("1234", (await self.inbox.execute("", ALICE)).console)
        self.assertTrue(self.msg.private and self.inbox.private)


PASSPHRASE = "blue-canoe-42x"


class SealedMailboxTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.folder / "users.toml"
        self.path.write_text("".join(f'[users.{s.public_key}]\nname = "{n}"\n\n'
                                     for s, n in [(ALICE, "Alice"), (ANN, "Ann"), (NONAME, "Noname")]))
        self.directory = Directory(path=self.path)
        self.directory.load()
        self.now = 50_000.0
        self.clock = 1_000.0
        self.enterContext(mock.patch("mesh_contingency.commands.mailbox.time.time", lambda: self.now))
        self.enterContext(mock.patch("mesh_contingency.commands.mailbox.time.monotonic", lambda: self.clock))
        self.enterContext(mock.patch("mesh_contingency.state.time.time", lambda: self.now))
        self.start()

    def start(self):
        state = State(self.folder)
        self.msg, self.inbox, self.clear, self.setpass = (
            cls(make_context(name, directory=self.directory, state=state)) for cls, name in
            [(MsgCommand, "msg"), (InboxCommand, "inbox"), (ClearInboxCommand, "clearinbox"),
             (SetPassCommand, "setpass")])

    def mailbox_text(self):
        return (self.folder / "mailbox.json").read_text()

    async def test_setpass_seals_new_messages(self):
        reply = (await self.setpass.execute(PASSPHRASE, ALICE)).reply
        self.assertEqual(reply, ["setpass: passphrase set; new messages to you will be sealed.",
                                 "A forgotten passphrase can't be recovered, and messages sealed with it are lost."])
        saved = tomllib.loads(self.path.read_text())["users"][ALICE.public_key]
        self.assertEqual(set(saved["inbox_key"]), {"public", "salt", "n"})
        self.assertNotIn(PASSPHRASE, self.path.read_text())

        result = await self.msg.execute("Alice meet at the shelter at 6", ANN)
        self.assertEqual(result.reply, "msg: saved for Alice (1 in their inbox)")
        self.assertEqual(result.console, "sealed message for Alice from Ann")
        self.assertNotIn("shelter", self.mailbox_text())
        self.assertIn('"from": "Ann"', self.mailbox_text())

        self.now += 600
        result = await self.inbox.execute(PASSPHRASE, ALICE)
        self.assertEqual(result.reply, ["Ann 10m ago: meet at the shelter at 6"])
        self.assertNotIn("shelter", result.console)
        self.start()  # still sealed and openable after a restart
        self.assertEqual((await self.inbox.execute(PASSPHRASE, ALICE)).reply, ["Ann 10m ago: meet at the shelter at 6"])
        self.assertEqual((await self.clear.execute("", ALICE)).reply, "clearinbox: deleted 1 message(s)")

    async def test_plain_inbox_shows_who_and_when(self):
        await self.setpass.execute(PASSPHRASE, ALICE)
        self.assertEqual((await self.inbox.execute("", ALICE)).reply, "inbox: no messages")
        await self.msg.execute("Alice first", ANN)
        self.now += 3600
        await self.msg.execute("Alice second", NONAME)
        result = await self.inbox.execute("", ALICE)
        self.assertEqual(result.reply, "inbox: 2 message(s) from Ann 1h ago, Noname just now. "
                                       "Send inbox <passphrase> to read.")
        # Not shown, so clearinbox keeps them.
        self.assertEqual((await self.clear.execute("", ALICE)).reply,
                         "clearinbox: deleted 0 message(s); 2 new one(s) kept, see inbox")

    async def test_wrong_passphrase(self):
        await self.setpass.execute(PASSPHRASE, ALICE)
        await self.msg.execute("Alice secret", ANN)
        with self.assertRaisesRegex(CommandError, "^inbox: wrong passphrase$"):
            await self.inbox.execute("blue-canoe-42y", ALICE)
        with self.assertRaisesRegex(CommandError, "^inbox: wrong passphrase$"):
            await self.inbox.execute("blue-canoe-42y 2", ALICE)

    async def test_without_a_passphrase_messages_stay_plain(self):
        await self.msg.execute("Ann hello", ALICE)
        self.assertIn("hello", self.mailbox_text())
        self.assertEqual((await self.inbox.execute("", ANN)).reply, ["Alice just now: hello"])

    async def test_messages_from_before_setpass_open_with_it(self):
        await self.msg.execute("Alice before", ANN)
        await self.setpass.execute(PASSPHRASE, ALICE)
        await self.msg.execute("Alice after", ANN)
        self.assertIn("2 message(s)", (await self.inbox.execute("", ALICE)).reply)
        self.assertEqual((await self.inbox.execute(PASSPHRASE, ALICE)).reply,
                         ["Ann just now: before", "Ann just now: after"])

    async def test_pages_with_a_passphrase(self):
        await self.setpass.execute(PASSPHRASE, ALICE)
        for i in range(10):
            await self.msg.execute(f"Alice message {i}", ANN)
        first = (await self.inbox.execute(PASSPHRASE, ALICE)).reply
        self.assertEqual(first[-1], "inbox: page 1 of 2; send inbox <passphrase> 2 for more")
        self.assertEqual((await self.inbox.execute(f"{PASSPHRASE} 2", ALICE)).reply,
                         [f"Ann just now: message {i}" for i in (7, 8, 9)])

    async def test_numeric_passphrase_is_not_a_page(self):
        await self.setpass.execute("123456789012", ALICE)
        await self.msg.execute("Alice digits", ANN)
        self.assertEqual((await self.inbox.execute("123456789012", ALICE)).reply, ["Ann just now: digits"])

    async def test_passphrase_rules(self):
        for text, why in [("a" * 11, "must be 12 to 16 characters"), ("a" * 17, "must be 12 to 16 characters"),
                          ("blue canoe 42", "can't contain spaces")]:
            with self.subTest(text=text), self.assertRaisesRegex(CommandError, f"^setpass: a passphrase {why}$"):
                await self.setpass.execute(text, ALICE)
        with self.assertRaisesRegex(CommandError, "^usage: setpass <passphrase>$"):
            await self.setpass.execute("", ALICE)
        for ok in ("a" * 12, "b" * 16):
            self.assertIn("passphrase set", (await self.setpass.execute(ok, ALICE)).reply[0])
        self.assertTrue(self.setpass.private)

    async def test_same_passphrase_again(self):
        await self.setpass.execute(PASSPHRASE, ALICE)
        key = self.directory.users[ALICE.public_key]["inbox_key"]
        self.assertEqual((await self.setpass.execute(PASSPHRASE, ALICE)).reply,
                         "setpass: that is already your passphrase")
        self.assertEqual(self.directory.users[ALICE.public_key]["inbox_key"], key)

    async def test_new_passphrase_without_sealed_messages(self):
        await self.setpass.execute(PASSPHRASE, ALICE)
        await self.setpass.execute("green-boat-77x", ALICE)
        await self.msg.execute("Alice hi", ANN)
        self.assertEqual((await self.inbox.execute("green-boat-77x", ALICE)).reply, ["Ann just now: hi"])

    async def test_new_passphrase_with_sealed_messages_asks_first(self):
        await self.setpass.execute(PASSPHRASE, ALICE)
        await self.msg.execute("Alice old secret", ANN)
        old_key = self.directory.users[ALICE.public_key]["inbox_key"]
        reply = (await self.setpass.execute("green-boat-77x", ALICE)).reply
        self.assertEqual(reply, ["setpass: your 1 sealed message(s) only open with your old passphrase, "
                                 "and will be deleted.",
                                 "Read them first with inbox <old passphrase>, or send the same setpass again "
                                 "within 5 min to confirm."])
        self.assertEqual(self.directory.users[ALICE.public_key]["inbox_key"], old_key)  # nothing changed yet
        self.assertEqual((await self.inbox.execute(PASSPHRASE, ALICE)).reply, ["Ann just now: old secret"])

        # A different passphrase starts over instead of confirming.
        self.assertIn("will be deleted", (await self.setpass.execute("other-pass-123", ALICE)).reply[0])
        self.assertIn("will be deleted", (await self.setpass.execute("green-boat-77x", ALICE)).reply[0])
        reply = (await self.setpass.execute("green-boat-77x", ALICE)).reply
        self.assertEqual(reply[-1], "setpass: deleted 1 message(s) sealed with the old passphrase.")
        self.assertEqual((await self.inbox.execute("green-boat-77x", ALICE)).reply, "inbox: no messages")

    async def test_confirmation_expires(self):
        await self.setpass.execute(PASSPHRASE, ALICE)
        await self.msg.execute("Alice old secret", ANN)
        await self.setpass.execute("green-boat-77x", ALICE)
        self.clock += CONFIRM_SECONDS
        self.assertIn("will be deleted", (await self.setpass.execute("green-boat-77x", ALICE)).reply[0])

    async def test_plain_messages_survive_a_passphrase_change(self):
        await self.msg.execute("Alice plain", ANN)
        await self.setpass.execute(PASSPHRASE, ALICE)
        await self.msg.execute("Alice sealed", ANN)
        await self.setpass.execute("green-boat-77x", ALICE)
        await self.setpass.execute("green-boat-77x", ALICE)
        self.assertEqual((await self.inbox.execute("green-boat-77x", ALICE)).reply, ["Ann just now: plain"])

    async def test_sealed_message_from_another_key(self):
        await self.setpass.execute(PASSPHRASE, ALICE)
        await self.msg.execute("Alice hi", ANN)
        # An admin replaces the key by hand, so the message can't be opened.
        self.directory.save_user(ALICE.public_key, {"name": "Alice", "inbox_key": new_inbox_key("green-boat-77x")})
        self.assertEqual((await self.inbox.execute("green-boat-77x", ALICE)).reply,
                         ["Ann just now: (sealed with another passphrase; can't be opened)"])
        self.directory.save_user(ALICE.public_key, {"name": "Alice"})
        self.assertEqual((await self.inbox.execute("", ALICE)).reply,
                         ["Ann just now: (sealed, and you have no passphrase now)"])

    async def test_broken_inbox_key(self):
        self.directory.save_user(ALICE.public_key, {"name": "Alice", "inbox_key": {"public": "zz"}})
        with self.assertRaisesRegex(CommandError, "^msg: Alice's inbox_key is broken; ask an admin$"):
            await self.msg.execute("Alice hi", ANN)
        with self.assertRaisesRegex(CommandError, "^inbox: your inbox_key is broken; ask an admin$"):
            await self.inbox.execute(PASSPHRASE, ALICE)
        self.assertIn("passphrase set", (await self.setpass.execute(PASSPHRASE, ALICE)).reply[0])


class NoticeAndExpiryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = 50_000.0
        self.clock = 1_000.0
        self.enterContext(mock.patch("mesh_contingency.commands.mailbox.time.time", lambda: self.now))
        self.enterContext(mock.patch("mesh_contingency.commands.mailbox.time.monotonic", lambda: self.clock))
        self.enterContext(mock.patch("mesh_contingency.state.time.time", lambda: self.now))
        self.start()

    def start(self, msg_options=None):
        self.sent = []
        state, commands = State(), {}
        for cls, name, options in [(MsgCommand, "msg", msg_options), (InboxCommand, "inbox", None),
                                   (ClearInboxCommand, "clearinbox", None)]:
            commands[name] = cls(make_context(name, options=options, users=USERS, state=state, sent=self.sent,
                                              commands=commands))
        self.msg, self.inbox, self.clear = commands["msg"], commands["inbox"], commands["clearinbox"]

    async def test_recipient_is_told_once_per_ten_minutes(self):
        await self.msg.execute("Alice one", ANN)
        await self.msg.execute("Alice two", ANN_LEE)
        self.assertEqual(self.sent, [(ALICE.public_key, "inbox: new message from Ann; send inbox to read")])
        self.clock += NOTICE_SECONDS
        await self.msg.execute("Alice three", ANN)
        self.assertEqual(len(self.sent), 2)
        self.assertNotIn("three", self.sent[-1][1])

    async def test_no_notice_to_yourself_or_when_turned_off(self):
        await self.msg.execute("Alice note to self", ALICE)
        self.assertEqual(self.sent, [])
        self.start({"notify": False})
        await self.msg.execute("Alice hi", ANN)
        self.assertEqual(self.sent, [])

    async def test_clearinbox_all(self):
        await self.msg.execute("Alice unread", ANN)
        self.assertEqual((await self.clear.execute("all", ALICE)).reply, "clearinbox: deleted 1 message(s)")
        self.assertEqual((await self.inbox.execute("", ALICE)).reply, "inbox: no messages")

    async def test_old_messages_expire(self):
        await self.msg.execute("Alice old", ANN)
        self.now += 29 * 86400
        await self.msg.execute("Alice newer", ANN)
        self.now += 86400 + 1
        self.assertEqual((await self.inbox.execute("", ALICE)).reply, ["Ann 1d ago: newer"])
        self.now += 29 * 86400
        self.assertEqual((await self.inbox.execute("", ALICE)).reply, "inbox: no messages")
        self.assertEqual(self.msg.boxes, {})

    async def test_keep_days(self):
        self.start({"keep_days": 0})
        await self.msg.execute("Alice forever", ANN)
        self.now += 400 * 86400
        self.assertEqual(len((await self.inbox.execute("", ALICE)).reply), 1)
        for bad in (-1, 1.5, True, "30"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "keep_days"):
                MsgCommand(make_context("msg", options={"keep_days": bad}))
        with self.assertRaisesRegex(ValueError, "notify"):
            MsgCommand(make_context("msg", options={"notify": "no"}))

if __name__ == "__main__":
    unittest.main()
