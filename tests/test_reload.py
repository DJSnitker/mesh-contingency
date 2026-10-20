import tempfile
import unittest
from pathlib import Path

from mesh_contingency.api import CommandError, Sender
from mesh_contingency.commands.reload import ReloadCommand
from mesh_contingency.directory import Directory
from mesh_contingency.testing import make_context

ADMIN = Sender("Admin", "ad" * 32)
DANA = "d0" * 32


class ReloadCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "users.toml"
        self.path.write_text(f'[admin]\nkeys = ["{ADMIN.public_key}"]\n')
        self.directory = Directory(path=self.path)
        self.directory.load()
        self.cmd = ReloadCommand(make_context("reload", directory=self.directory))

    async def test_reloads_straight_away(self):
        self.path.write_text(self.path.read_text() + f'[users.{DANA}]\nname = "Dana"\n')
        result = await self.cmd.execute("", ADMIN)
        self.assertEqual(result.reply, "reload: added Dana")
        self.assertEqual(result.console, "")
        self.assertIn(DANA, self.directory.users)

    async def test_no_changes(self):
        self.assertEqual((await self.cmd.execute("", ADMIN)).reply, "reload: no changes")

    async def test_bad_file_keeps_users_and_says_why(self):
        self.path.write_text("[users.d0d0d0d0d0d0]\n")
        with self.assertRaisesRegex(CommandError, r"^reload: users.toml not reloaded: \[users\]: "
                                                  r"'d0d0d0d0d0d0' is not a full public key"):
            await self.cmd.execute("", ADMIN)
        self.assertEqual(self.directory.admins, {ADMIN.public_key})


if __name__ == "__main__":
    unittest.main()
