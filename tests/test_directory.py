import asyncio
import os
import tempfile
import tomllib
import unittest
from pathlib import Path

from mesh_contingency.directory import Directory, DirectoryError, parse, summarize

ALICE = "a1" * 32
BOB = "b0" * 32
ADMIN = "ad" * 32

USERS = f"""
[admin]
keys = ["{ADMIN}"]

[users.{ALICE}]
name = "Alice"
quickim = "a@example.com"
"""


def parse_text(text):
    return parse(tomllib.loads(text))


class ParseTest(unittest.TestCase):
    def test_users_and_admins(self):
        users, admins = parse_text(USERS)
        self.assertEqual(users, {ALICE: {"name": "Alice", "quickim": "a@example.com"}})
        self.assertEqual(admins, frozenset({ADMIN}))

    def test_keys_normalized_to_lowercase(self):
        users, admins = parse_text(f'[admin]\nkeys = [" {ADMIN.upper()} "]\n[users.{ALICE.upper()}]\n')
        self.assertEqual((set(users), admins), ({ALICE}, {ADMIN}))

    def test_empty_file(self):
        self.assertEqual(parse_text(""), ({}, frozenset()))

    def test_mistakes(self):
        for text, error in [
            (f"[users.{ALICE[:12]}]", r"\[users\]: 'a1a1a1a1a1a1' is not a full public key"),
            ('[admin]\nkeys = ["a1a1a1a1a1a1"]', r"\[admin\] keys: .* is not a full public key"),
            ("[admin]\nkeys = [42]", r"\[admin\] keys: 42 is not a full public key"),
            (f'[admin]\nkeys = "{ADMIN}"', r"\[admin\] keys must be a list"),
            (f'[admin]\nkey = ["{ADMIN}"]', r"\[admin\] must only hold keys"),
            ("[permissions]", "unknown section"),
            (f'[users]\n"{ALICE}" = "Alice"', r"must be a table"),
            (f'[users.{ALICE}]\n[users.{ALICE.upper()}]', "listed twice"),
            (f"[users.{ALICE}]\nname = 3", "name must be text"),
        ]:
            with self.subTest(text=text), self.assertRaisesRegex(DirectoryError, error):
                parse_text(text)

    def test_errors_never_show_a_whole_key(self):
        long_key = ALICE + "00"  # one byte too long
        with self.assertRaises(DirectoryError) as caught:
            parse_text(f'[admin]\nkeys = ["{long_key}"]')
        self.assertNotIn(ALICE, str(caught.exception))


class SummarizeTest(unittest.TestCase):
    def test_changes(self):
        old = {ALICE: {"name": "Alice", "quickim": "a@example.com"}, BOB: {"name": "Bob"}}
        new = {ALICE: {"name": "Alice", "quickim": "new@example.com"}, ADMIN: {}}
        self.assertEqual(summarize(old, frozenset(), new, frozenset({ALICE})),
                         "added adadadadadad; removed Bob; changed Alice; admin added Alice")
        self.assertEqual(summarize(new, frozenset({BOB}), new, frozenset()), "admin removed b0b0b0b0b0b0")

    def test_no_changes(self):
        self.assertEqual(summarize({}, frozenset(), {}, frozenset()), "no changes")


class FromConfigTest(unittest.TestCase):
    def test_defaults_next_to_the_config(self):
        d = Directory.from_config({}, "/srv/bot/config.toml")
        self.assertEqual((d.path, d.reload_seconds), (Path("/srv/bot/users.toml"), 5))

    def test_settings(self):
        d = Directory.from_config({"directory": {"file": "people/u.toml", "reload_seconds": 0}}, "/srv/bot/config.toml")
        self.assertEqual((d.path, d.reload_seconds), (Path("/srv/bot/people/u.toml"), 0))
        d = Directory.from_config({"directory": {"file": "/etc/u.toml"}}, "/srv/bot/config.toml")
        self.assertEqual(d.path, Path("/etc/u.toml"))

    def test_users_left_in_config_toml(self):
        for section in ("users", "admin"):
            with self.subTest(section=section), self.assertRaisesRegex(SystemExit, "now go in their own file"):
                Directory.from_config({section: {}}, "config.toml")

    def test_mistakes(self):
        for section in [{"reload_seconds": -1}, {"reload_seconds": True}, {"reload_seconds": "5"},
                        {"file": ""}, {"file": 3}, {"path": "u.toml"}]:
            with self.subTest(section=section), self.assertRaises(SystemExit):
                Directory.from_config({"directory": section}, "config.toml")


class FileTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.folder / "users.toml"
        self.directory = Directory(path=self.path)
        self.changes = []
        self.directory.on_change.append(self.changes.append)
        self.version = 0

    def write(self, text):
        """Write the file with a new modification time, as a later save would."""
        self.path.write_text(text)
        self.version += 1
        os.utime(self.path, ns=(self.version * 10**9, self.version * 10**9))

    def test_load(self):
        self.write(USERS)
        self.assertTrue(self.directory.load())
        self.assertEqual(set(self.directory.users), {ALICE})
        self.assertEqual(self.directory.admins, {ADMIN})
        self.assertEqual(self.changes, ["added Alice; admin added adadadadadad"])

    def test_load_missing_file(self):
        self.assertFalse(self.directory.load())
        self.assertEqual((self.directory.users, self.directory.admins), ({}, frozenset()))

    def test_load_invalid_file_exits(self):
        self.write("[users.abc]")
        with self.assertRaisesRegex(SystemExit, "users.toml: .*not a full public key"):
            self.directory.load()

    def test_change_used_once_the_file_is_stable(self):
        self.write(USERS)
        self.directory.load()
        self.assertIsNone(self.directory.check())  # unchanged
        self.write(USERS + f"[users.{BOB}]\nname = 'Bob'\n")
        self.assertIsNone(self.directory.check())  # changed: wait for one more check
        self.assertNotIn(BOB, self.directory.users)
        self.assertEqual(self.directory.check(), "added Bob")
        self.assertIn(BOB, self.directory.users)
        self.assertIsNone(self.directory.check())

    def test_still_changing_file_waits(self):
        self.write(USERS)
        self.directory.load()
        self.write("[users.")  # half saved
        self.assertIsNone(self.directory.check())
        self.write(USERS + f"[users.{BOB}]\n")  # save finished
        self.assertIsNone(self.directory.check())
        self.assertEqual(self.directory.check(), "added b0b0b0b0b0b0")

    def test_force_reads_straight_away(self):
        self.write(USERS)
        self.directory.load()
        self.assertEqual(self.directory.check(force=True), "no changes")
        self.write("")
        self.assertEqual(self.directory.check(force=True), "removed Alice; admin removed adadadadadad")

    def test_bad_edit_keeps_the_current_users(self):
        self.write(USERS)
        self.directory.load()
        users, admins = self.directory.users, self.directory.admins
        self.write(USERS + "[users.oops]\n")
        self.directory.check()
        with self.assertRaisesRegex(DirectoryError, "not a full public key"):
            self.directory.check()
        self.assertIsNone(self.directory.check())  # reported once per bad version
        self.assertIs(self.directory.users, users)
        self.assertIs(self.directory.admins, admins)
        self.write(USERS.replace("Alice", "Alicia"))  # fixed
        self.directory.check()
        self.assertEqual(self.directory.check(), "changed Alicia")

    def test_bad_toml(self):
        self.write("[users")
        with self.assertRaisesRegex(DirectoryError, "not valid TOML"):
            self.directory.check(force=True)

    def test_deleted_file_keeps_the_current_users(self):
        self.write(USERS)
        self.directory.load()
        self.path.unlink()
        self.directory.check()
        with self.assertRaisesRegex(DirectoryError, "file not found"):
            self.directory.check()
        self.assertIsNone(self.directory.check())
        self.assertIn(ALICE, self.directory.users)

    def test_file_created_after_startup(self):
        self.directory.load()
        self.write(USERS)
        self.directory.check()
        self.assertEqual(self.directory.check(), "added Alice; admin added adadadadadad")


class WatchTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.folder / "users.toml"
        self.path.write_text(USERS)
        self.errors = []
        self.wake = asyncio.Event()

    async def watch(self, reload_seconds):
        directory = Directory(path=self.path, reload_seconds=reload_seconds)
        directory.load()
        task = asyncio.create_task(directory.watch(self.wake, self.errors.append))
        self.addCleanup(task.cancel)
        return directory

    async def wait_for(self, condition):
        for _ in range(200):
            if condition():
                return
            await asyncio.sleep(0.01)
        self.fail("timed out")

    async def test_polls_for_changes(self):
        directory = await self.watch(0.01)
        self.path.write_text(USERS + f"[users.{BOB}]\n")
        os.utime(self.path, ns=(1, 1))
        await self.wait_for(lambda: BOB in directory.users)

    async def test_reports_errors(self):
        await self.watch(0.01)
        self.path.write_text("[users")
        await self.wait_for(lambda: self.errors)
        self.assertIn("not valid TOML", self.errors[0])

    async def test_wake_forces_a_reload_when_not_polling(self):
        directory = await self.watch(0)
        self.path.write_text("")
        await asyncio.sleep(0.05)
        self.assertIn(ALICE, directory.users)  # not polling
        self.wake.set()
        await self.wait_for(lambda: not directory.users)


if __name__ == "__main__":
    unittest.main()
