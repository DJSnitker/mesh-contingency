import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from meshcore import EventType

from mesh_contingency.api import MAX_REPLY_LEN, CommandError, Sender
from mesh_contingency.commands.alert import AlertCommand
from mesh_contingency.commands.history import HistoryCommand
from mesh_contingency.commands.join import ApproveCommand, DenyCommand, JoinCommand
from mesh_contingency.commands.mailbox import SetPassCommand
from mesh_contingency.commands.status import ClearStatusCommand, OkCommand
from mesh_contingency.commands.users import LeaveCommand, RemoveCommand, ResetPassCommand
from mesh_contingency.directory import Directory
from mesh_contingency.state import HISTORY_FILE, MAX_HISTORY, State
from mesh_contingency.testing import FakeMeshCore, make_context

ADMIN = Sender("admin-node", "ad" * 32)
ALICE = Sender("alice-node", "a1" * 32)
BOB = Sender("BobNode", "b0" * 32)
CAROL = Sender("CarolNode", "c0" * 32)


class RecordTest(unittest.TestCase):
    def test_saved_newest_last_and_trimmed(self):
        with tempfile.TemporaryDirectory() as folder:
            state = State(folder)
            for i in range(MAX_HISTORY + 3):
                state.record("Admin", f"action {i}")
            saved = json.loads((Path(folder) / HISTORY_FILE).read_text())["entries"]
        self.assertEqual(len(saved), MAX_HISTORY)
        self.assertEqual(saved[-1]["what"], f"action {MAX_HISTORY + 2}")
        self.assertEqual(saved[0]["what"], "action 3")
        self.assertEqual(saved[-1]["by"], "Admin")


class HistoryCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = State()
        self.history = HistoryCommand(make_context("history", state=self.state))

    async def test_nothing_yet(self):
        self.assertEqual((await self.history.execute("", ADMIN)).reply, "history: nothing yet")

    async def test_newest_first(self):
        with mock.patch("mesh_contingency.state.time.time", return_value=time.time() - 7200):
            self.state.record("Admin", "approved Sam (5a3e1c7b9d20)")
        self.state.record("Admin", "removed Sam (5a3e1c7b9d20), 0 message(s) deleted")
        reply = (await self.history.execute("", ADMIN)).reply
        self.assertEqual(reply, ["history (2): just now Admin: removed Sam (5a3e1c7b9d20), 0 message(s) deleted; "
                                 "2h ago Admin: approved Sam (5a3e1c7b9d20)"])

    async def test_pages(self):
        for i in range(60):
            self.state.record("Admin", f"approved Person{i:02} (5a3e1c7b9d20)")
        reply = (await self.history.execute("", ADMIN)).reply
        self.assertTrue(all(len(message) <= MAX_REPLY_LEN for message in reply))
        self.assertIn("Person59", reply[0])
        pages = int(reply[-1].split(" of ")[1].split(";")[0])
        self.assertEqual(reply[-1], f"history: page 1 of {pages}; send history 2 for more")
        last = (await self.history.execute(str(pages), ADMIN)).reply
        self.assertIn("Person00", last[-1])  # oldest last, with no "for more"

    async def test_usage(self):
        with self.assertRaisesRegex(CommandError, r"^usage: history \[page\]$"):
            await self.history.execute("all", ADMIN)


class RecordedActionsTest(unittest.IsolatedAsyncioTestCase):
    """Each admin action (and leave) adds one entry, naming who did it."""

    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = self.folder / "users.toml"
        path.write_text(f'[admin]\nkeys = ["{ADMIN.public_key}"]\n\n[users.{ADMIN.public_key}]\nname = "Admin"\n\n'
                        f'[users.{ALICE.public_key}]\nname = "Alice"\n')
        self.directory = Directory(path=path)
        self.directory.load()
        self.state = State(self.folder)
        self.radio = FakeMeshCore()
        self.commands = {}

    def make(self, cls, name):
        self.commands[name] = cls(make_context(name, directory=self.directory, state=self.state, radio=self.radio,
                                               commands=self.commands))
        return self.commands[name]

    def recorded(self):
        return [(entry["by"], entry["what"]) for entry in self.state.store(HISTORY_FILE).data.get("entries", [])]

    async def test_join_approve_deny(self):
        join, approve, deny = (self.make(cls, name) for cls, name in
                               [(JoinCommand, "join"), (ApproveCommand, "approve"), (DenyCommand, "deny")])
        await join.execute("", BOB)
        await join.execute("", CAROL)
        self.assertEqual(self.recorded(), [])  # asking isn't an admin action
        await approve.execute("bobnode", ADMIN)
        await deny.execute("carolnode", ADMIN)
        self.assertEqual(self.recorded(), [("Admin", "approved BobNode (b0b0b0b0b0b0)"),
                                           ("Admin", "denied CarolNode (c0c0c0c0c0c0)")])

    async def test_resetpass_remove_leave(self):
        resetpass, remove, leave = (self.make(cls, name) for cls, name in [
            (ResetPassCommand, "resetpass"), (RemoveCommand, "remove"), (LeaveCommand, "leave")])
        await self.make(SetPassCommand, "setpass").execute("blue-canoe-42x", ALICE)
        await resetpass.execute("alice", ADMIN)
        await remove.execute("alice", ADMIN)
        self.assertEqual(len(self.recorded()), 1)  # remove asks first
        await remove.execute("alice", ADMIN)
        await leave.execute("", ADMIN)
        await leave.execute("", ADMIN)
        self.assertEqual(self.recorded(), [
            ("Admin", "cleared Alice's passphrase (a1a1a1a1a1a1), 0 sealed message(s) deleted"),
            ("Admin", "removed Alice (a1a1a1a1a1a1), 0 message(s) deleted"),
            ("Admin", "left the users (adadadadadad)"),
        ])

    async def test_clearstatus_and_alert(self):
        await self.make(OkCommand, "ok").execute("fine", ALICE)
        await self.make(ClearStatusCommand, "clearstatus").execute("", ADMIN)
        alert = self.make(AlertCommand, "alert")
        alert.send_gap = 0
        with mock.patch("mesh_contingency.commands.alert.fetch_alerts", return_value=("79601", "Abilene, TX", [])):
            await alert.execute("79601", ADMIN)
        self.assertEqual(self.recorded(), [("Admin", "cleared 1 check-in(s)"),
                                           ("Admin", "posted 79601 alerts to #contingency-wx")])
        self.assertEqual(self.radio.channel_sent[-1][1], "No alerts active for 79601")
        self.assertEqual(self.radio.channel_result.type, EventType.OK)


if __name__ == "__main__":
    unittest.main()
