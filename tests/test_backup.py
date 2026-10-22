import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from mesh_contingency.api import CommandError, Sender
from mesh_contingency.backup import BackupError, Backups, BackupSettings, load_backup
from mesh_contingency.commands.backup import BackupCommand
from mesh_contingency.commands.health import HealthCommand
from mesh_contingency.directory import Directory
from mesh_contingency.state import State
from mesh_contingency.testing import FakeMeshCore, make_context
from mesh_contingency.watch import NodeWatch, WatchSettings

DOUG = Sender("Doug", "a1" * 32)


def mode(path):
    return os.stat(path).st_mode & 0o777


class LoadBackupTest(unittest.TestCase):
    def test_defaults(self):
        settings = load_backup({}, "/srv/node")
        self.assertEqual((settings.to, settings.every_hours, settings.keep), ("~/MeshContingencyBackups", 24, 7))
        self.assertEqual(settings.folder, Path.home() / "MeshContingencyBackups")

    def test_settings(self):
        settings = load_backup({"backup": {"to": "/mnt/usb/backups", "every_hours": 0, "keep": 3}}, "/srv/node")
        self.assertEqual(settings, BackupSettings("/mnt/usb/backups", 0, 3, Path("/mnt/usb/backups")))

    def test_relative_to_the_config(self):
        self.assertEqual(load_backup({"backup": {"to": "copies"}}, "/srv/node").folder, Path("/srv/node/copies"))

    def test_mistakes(self):
        for section, message in [
            ({"folder": "x"}, r"^\[backup\] may only set every_hours, keep, to\.$"),
            ({"to": ""}, r"to must be a folder"),
            ({"to": 5}, r"to must be a folder"),
            ({"every_hours": -1}, r"every_hours must be a number of hours"),
            ({"keep": 0}, r"keep must be a whole number, at least 1"),
            ({"keep": 2.5}, r"keep must be a whole number"),
        ]:
            with self.assertRaisesRegex(SystemExit, message):
                load_backup({"backup": section}, "/srv/node")


class BackupsTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.out = self.enterContext(mock.patch("builtins.print"))
        self.data = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.target = Path(self.enterContext(tempfile.TemporaryDirectory())) / "Backups"
        self.config = self.data / "config.toml"
        self.config.write_text("[commands]\n")
        users = self.data / "users.toml"
        users.write_text("[admin]\n")
        users.chmod(0o600)
        (self.data / "status.json").write_text("{}")
        (self.data / "status.json").chmod(0o600)
        (self.data / "history.json.tmp").write_text("{}")  # half written: not backed up
        (self.data / "backups").mkdir()
        (self.data / "backups" / "users-20261020-221500.toml").write_text("old")
        self.state = State(self.data)
        self.directory = Directory({}, set(), path=users)
        self.backups = self.new_backups()

    def new_backups(self, **settings):
        settings = BackupSettings(str(self.target), settings.get("every_hours", 24), settings.get("keep", 7),
                                  self.target)
        self.state.backups = Backups(settings, self.state, self.config, self.directory)
        return self.state.backups


class BackupsTest(BackupsTestCase):
    async def test_copies_everything_privately(self):
        name, copied, removed = await self.backups.make("Doug")
        folder = self.target / name
        self.assertEqual(sorted(str(p.relative_to(folder)) for p in folder.rglob("*")),
                         ["backups", "backups/users-20261020-221500.toml", "config.toml", "status.json",
                          "users.toml"])
        self.assertEqual((copied, removed), (4, 0))
        self.assertEqual((folder / "users.toml").read_text(), "[admin]\n")
        self.assertEqual(mode(folder / "users.toml"), 0o600)
        self.assertEqual(mode(folder / "status.json"), 0o600)
        self.assertEqual(mode(self.target), 0o700)
        self.assertEqual(mode(folder), 0o700)
        self.assertEqual(mode(folder / "backups"), 0o700)

    async def test_recorded(self):
        self.assertIsNone(self.backups.last)
        name, _, _ = await self.backups.make("Doug")
        self.assertAlmostEqual(self.backups.last, time.time(), delta=5)
        entry = self.state.store("history.json").data["entries"][-1]
        self.assertEqual((entry["by"], entry["what"]), ("Doug", f"backed up 4 file(s) to {name}"))
        # The time of this backup is in the next one.
        name, copied, _ = await self.backups.make("auto")
        self.assertTrue((self.target / name / "backup.json").exists())

    async def test_keeps_the_newest(self):
        backups = self.new_backups(keep=3)
        (self.target / "notes").mkdir(parents=True)  # not a backup: left alone
        names = [(await backups.make("auto"))[0] for _ in range(12)]
        self.assertEqual([p.name for p in backups.snapshots()], names[-3:])
        self.assertTrue((self.target / "notes").is_dir())

    async def test_existing_folder_keeps_its_permissions(self):
        self.target.mkdir(mode=0o755)
        self.target.chmod(0o755)
        await self.backups.make("auto")
        self.assertEqual(mode(self.target), 0o755)

    async def test_failure(self):
        self.target.parent.mkdir(exist_ok=True)
        self.target.write_text("a file, not a folder")
        with self.assertRaisesRegex(BackupError, "^File exists$|Not a directory"):
            await self.backups.make("auto")
        self.assertTrue(self.backups.failing)
        self.assertEqual(self.state.last_error[1], "backup failed")
        self.target.unlink()
        await self.backups.make("auto")
        self.assertIsNone(self.backups.failing)

    def test_due(self):
        self.assertEqual(self.backups.seconds_until_due(), 0)
        self.backups.store.data["last"] = time.time() - 3600
        self.assertAlmostEqual(self.backups.seconds_until_due(), 23 * 3600, delta=5)
        self.backups.store.data["last"] = time.time() - 25 * 3600
        self.assertEqual(self.backups.seconds_until_due(), 0)

    def test_same_disk(self):
        self.assertTrue(self.backups.same_disk())  # both under the temporary folder's disk

    def test_describe(self):
        self.assertEqual(self.backups.describe(), f"every 24 h to {self.target} (newest 7 kept)")
        self.assertEqual(self.new_backups(every_hours=0).describe(),
                         f"only with backup to {self.target} (newest 7 kept)")


class BackupCommandTest(BackupsTestCase):
    def command(self):
        return BackupCommand(make_context("backup", state=self.state))

    async def test_backs_up_now(self):
        result = await self.command().execute("", DOUG)
        (folder,) = self.backups.snapshots()
        self.assertEqual(result.reply, f"backup: 4 file(s) saved in {self.target}/{folder.name}; newest 7 kept")

    async def test_usage(self):
        with self.assertRaisesRegex(CommandError, "^usage: backup$"):
            await self.command().execute("now", DOUG)

    async def test_not_set_up(self):
        with self.assertRaisesRegex(CommandError, "backups aren't set up yet"):
            await BackupCommand(make_context("backup", state=State())).execute("", DOUG)

    async def test_failure(self):
        self.target.parent.mkdir(exist_ok=True)
        self.target.write_text("a file")
        with self.assertRaisesRegex(CommandError, r"^backup: failed, .+; see the console$"):
            await self.command().execute("", DOUG)


class BackupWatchAndHealthTest(BackupsTestCase):
    async def test_watch_and_health(self):
        notices = []
        radio = FakeMeshCore()
        # Only the backup: no battery check, and the radio's start time already known.
        watch = self.state.watch = NodeWatch(radio, WatchSettings(battery_volts=0), self.state, self.directory,
                                             notices.append)
        await watch.check()
        self.assertEqual(notices, [])
        health = HealthCommand(make_context("health", radio=radio, state=self.state, directory=self.directory))

        async def health_text():
            return " ".join((await health.execute("", None)).reply)

        self.assertIn("no backup yet", await health_text())
        self.target.parent.mkdir(exist_ok=True)
        self.target.write_text("a file")
        with self.assertRaises(BackupError):
            await self.backups.make("auto")
        await watch.check()
        self.assertEqual(len(notices), 1)
        self.assertRegex(notices[0], rf"^Node problem: backup to {self.target} failing: .+")
        self.assertIn("backup failing: ", await health_text())
        self.assertIn("watch: backup failing", await health_text())
        self.target.unlink()
        await self.backups.make("auto")
        await watch.check()
        self.assertEqual(notices[1:], ["Node ok again: a backup was made"])
        self.assertIn("last backup just now", await health_text())


if __name__ == "__main__":
    unittest.main()
