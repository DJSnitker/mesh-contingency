"""The replies the phone app reads (tests/fixtures/app_replies.json) are what
the bot really sends. The app's tests check it reads the same file."""

import contextlib
import io
import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from mesh_contingency.api import Sender, split_reply
from mesh_contingency.bot import UNRECOGNIZED_REPLY
from mesh_contingency.commands.join import ApproveCommand, JoinCommand
from mesh_contingency.commands.mailbox import ClearInboxCommand, InboxCommand, MsgCommand, SetPassCommand
from mesh_contingency.commands.users import WhoAmICommand
from mesh_contingency.directory import Directory
from mesh_contingency.running import run_command
from mesh_contingency.state import State
from mesh_contingency.testing import make_context

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = json.loads((ROOT / "tests/fixtures/app_replies.json").read_text(encoding="utf-8"))
# The commands the app sends, with the permissions the example config gives them.
COMMANDS = {"join": JoinCommand, "approve": ApproveCommand, "whoami": WhoAmICommand, "msg": MsgCommand,
            "inbox": InboxCommand, "clearinbox": ClearInboxCommand, "setpass": SetPassCommand}
PERMISSIONS = tomllib.loads((ROOT / "config.example.toml").read_text(encoding="utf-8"))["commands"]


class Node:
    """The fixtures' node: its users and admins, and the app's commands."""

    def __init__(self, folder):
        self.senders = {name: Sender(name, byte * 32) for name, byte in FIXTURES["senders"].items()}
        lines = [f'[admin]\nkeys = [{", ".join(json.dumps(self.senders[a].public_key) for a in FIXTURES["admins"])}]\n']
        for name, settings in FIXTURES["users"].items():
            lines.append(f"[users.{self.senders[name].public_key}]\nname = {json.dumps(name)}")
            lines += [f"{setting} = {json.dumps(value)}" for setting, value in settings.items()]
        path = folder / "users.toml"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.directory = Directory(path=path)
        self.directory.load()
        self.sent = []
        state, self.commands = State(folder), {}
        for name, cls in COMMANDS.items():
            command = cls(make_context(name, directory=self.directory, state=state, sent=self.sent,
                                       commands=self.commands))
            command.permission = PERMISSIONS[name]["permission"]
            self.commands[name] = command
        self.state = state

    async def send(self, who, text):
        """What the node replies to `who` sending `text`, as mesh messages."""
        sender = self.senders[who]
        name, _, rest = text.partition(" ")
        command = self.commands[name]
        users, admins = self.directory.users, self.directory.admins
        allowed = {"public": True, "user": sender.public_key in users,
                   "admin": sender.public_key in admins}[command.permission]
        if not allowed:
            return [UNRECOGNIZED_REPLY]
        with contextlib.redirect_stdout(io.StringIO()):  # the bot's console lines
            return (await run_command(command, rest, sender, self.state)).messages


class AppRepliesTest(unittest.IsolatedAsyncioTestCase):
    async def test_each_reply_is_what_the_bot_sends(self):
        for case in FIXTURES["cases"]:
            with self.subTest(case["name"]):
                if case.get("split"):
                    self.assertEqual(split_reply(case["text"]), case["reply"])
                    self.assertGreater(len(case["reply"]), 1, "a split case should need several parts")
                    continue
                node = Node(Path(self.enterContext(tempfile.TemporaryDirectory())))
                for who, text in case.get("before", []):
                    await node.send(who, text)
                del node.sent[:]
                reply = await node.send(case["as"], case["send"])
                if "to" in case:
                    key = node.senders[case["to"]].public_key
                    reply = [text for to, text in node.sent if to == key]
                self.assertEqual(reply, case["reply"])

    def test_the_app_reads_the_same_file(self):
        spec = (ROOT / "app/src/app/node/replies.spec.ts").read_text(encoding="utf-8")
        self.assertIn("tests/fixtures/app_replies.json", spec)


if __name__ == "__main__":
    unittest.main()
