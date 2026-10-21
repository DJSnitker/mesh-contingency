import asyncio
import os
import tempfile
import tomllib
import unittest
from pathlib import Path

from mesh_contingency.directory import (
    BACKUPS,
    AmbiguousUser,
    Directory,
    DirectoryError,
    find_user,
    parse,
    possessive,
    summarize,
    toml_value,
    unquote,
    with_user,
)

ALICE = "a1" * 32
BOB = "b0" * 32
ADMIN = "ad" * 32

USERS = f"""
[admin]
keys = ["{ADMIN}"]

[users.{ALICE}]
name = "Alice"
qm = "a@example.com"
"""


def parse_text(text):
    return parse(tomllib.loads(text))


class ParseTest(unittest.TestCase):
    def test_users_and_admins(self):
        users, admins = parse_text(USERS)
        self.assertEqual(users, {ALICE: {"name": "Alice", "qm": "a@example.com"}})
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
        old = {ALICE: {"name": "Alice", "qm": "a@example.com"}, BOB: {"name": "Bob"}}
        new = {ALICE: {"name": "Alice", "qm": "new@example.com"}, ADMIN: {}}
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


class TomlValueTest(unittest.TestCase):
    def test_round_trip(self):
        for value in ["plain", 'quote " back\\slash', "new\nline\ttab\x7fdel\x01", "émoji 😀", True, 3, 2.5,
                      ["a", "b"], [], {"x": 1, "two words": ["y"]}]:
            with self.subTest(value=value):
                self.assertEqual(tomllib.loads(f"v = {toml_value(value)}")["v"], value)

    def test_unsupported(self):
        with self.assertRaises(ValueError):
            toml_value(None)


class WithUserTest(unittest.TestCase):
    def test_replaces_only_that_section(self):
        text = (f"# top\n[admin]\nkeys = []\n\n# Alice's settings\n[users.{ALICE}]  # comment\nname = 'Alice'\n"
                f"qm = [\n  'a@example.com',\n]\n\n# Bob next\n[users.{BOB}]\nname = 'Bob'\n")
        new = with_user(text, ALICE, {"name": "Alice", "qm": "new@example.com"})
        self.assertEqual(new, f"# top\n[admin]\nkeys = []\n\n# Alice's settings\n[users.{ALICE}]\nname = \"Alice\"\n"
                              f"qm = \"new@example.com\"\n\n# Bob next\n[users.{BOB}]\nname = 'Bob'\n")

    def test_finds_upper_case_and_quoted_headers(self):
        for header in (f"[users.{ALICE.upper()}]", f'[ users . "{ALICE}" ]'):
            with self.subTest(header=header):
                new = with_user(f"{header}\nname = 'A'\n", ALICE, {"name": "B"})
                self.assertEqual(new, f'[users.{ALICE}]\nname = "B"\n')

    def test_adds_a_new_user_at_the_end(self):
        self.assertEqual(with_user("[admin]\nkeys = []\n\n\n", BOB, {"name": "Bob"}),
                         f'[admin]\nkeys = []\n\n[users.{BOB}]\nname = "Bob"\n')
        self.assertEqual(with_user("", BOB, {}), f"[users.{BOB}]\n")


class SaveUserTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.folder / "users.toml"
        self.path.write_text("# my notes\n" + USERS)
        self.path.chmod(0o640)
        self.directory = Directory(path=self.path)
        self.directory.load()

    def test_save_several_users_at_once(self):
        changes = {ALICE: {"name": "Ridge Base 1", "qm": "alice@example.com"}, BOB: {"name": "Bob's T-Deck"}}
        self.assertEqual(self.directory.save_users(changes), "added Bob's T-Deck; changed Ridge Base 1")
        self.assertEqual(self.directory.users[ALICE]["name"], "Ridge Base 1")
        self.assertEqual(len(list((self.folder / "backups").iterdir())), 1)  # one backup for both

    def test_add_a_user(self):
        self.assertEqual(self.directory.save_user(BOB, {"name": "Bob"}), "added Bob")
        self.assertEqual(self.directory.users[BOB], {"name": "Bob"})
        self.assertTrue(self.path.read_text().startswith("# my notes\n"))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)  # permissions kept
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["backups", "users.toml"])  # no temp file

    def test_the_old_version_is_backed_up(self):
        old = self.path.read_text()
        self.directory.save_user(BOB, {"name": "Bob"})
        backups = list((self.folder / "backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertRegex(backups[0].name, r"^users-\d{8}-\d{6}\.toml$")
        self.assertEqual(backups[0].read_text(), old)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o640)  # as private as the file
        self.assertEqual((self.folder / "backups").stat().st_mode & 0o777, 0o700)

    def test_only_the_newest_backups_are_kept(self):
        versions = []
        for i in range(BACKUPS + 2):
            versions.append(self.path.read_text())
            self.directory.save_user(BOB, {"name": f"Bob{i}"})
        backups = sorted((self.folder / "backups").iterdir(), key=lambda p: p.stat().st_mtime_ns)
        self.assertEqual([p.read_text() for p in backups], versions[-BACKUPS:])

    def test_nothing_is_backed_up_when_a_write_is_refused(self):
        self.path.write_text(f"[users.{ALICE}]\nname = 'Alice'\n[users.{ALICE}.extra]\nx = 1\n")
        with self.assertRaises(DirectoryError):
            self.directory.save_user(ALICE, {"name": "Alice", "extra": {"x": 1}, "qm": "a@example.com"})
        self.assertFalse((self.folder / "backups").exists())

    def test_change_a_user(self):
        self.assertEqual(self.directory.save_user(ALICE, {"name": "Alice", "qm": "b@example.com"}),
                         "changed Alice")
        self.assertEqual(parse_text(self.path.read_text())[0][ALICE]["qm"], "b@example.com")

    def test_new_file(self):
        self.path.unlink()
        self.directory.save_user(BOB, {"name": "Bob"})
        self.assertEqual(self.path.read_text(), f'[users.{BOB}]\nname = "Bob"\n')
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_bad_file_is_not_touched(self):
        self.path.write_text("[users")
        with self.assertRaisesRegex(DirectoryError, "not valid TOML.*fix it first"):
            self.directory.save_user(BOB, {"name": "Bob"})
        self.assertEqual(self.path.read_text(), "[users")

    def test_section_it_cannot_rewrite_is_not_touched(self):
        text = f"[users.{ALICE}]\nname = 'Alice'\n[users.{ALICE}.extra]\nx = 1\n"
        self.path.write_text(text)
        with self.assertRaisesRegex(DirectoryError, "edit Alice's section by hand"):
            self.directory.save_user(ALICE, {"name": "Alice", "extra": {"x": 1}, "qm": "a@example.com"})
        self.assertEqual(self.path.read_text(), text)

    def test_in_memory(self):
        directory = Directory({ALICE: {"name": "Alice"}})
        self.assertEqual(directory.save_user(BOB, {"name": "Bob"}), "added Bob")
        self.assertEqual(set(directory.users), {ALICE, BOB})

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


class FindUserTest(unittest.TestCase):
    USERS = {ALICE: {"name": "Ann"}, BOB: {"name": "Ann Lee"}, ADMIN: {}}

    def test_names(self):
        self.assertEqual(find_user(self.USERS, "ann lee hi there"), (BOB, "hi there"))
        self.assertEqual(find_user(self.USERS, "ANN hi"), (ALICE, "hi"))
        self.assertEqual(find_user(self.USERS, "Ann"), (ALICE, ""))
        self.assertIsNone(find_user(self.USERS, "Annie hi"))

    def test_radio_names_with_spaces_and_punctuation(self):
        users = {ALICE: {"name": "Ridge Base 1"}, BOB: {"name": "Base #2 North"}}
        self.assertEqual(find_user(users, "ridge base 1 meet at 5"), (ALICE, "meet at 5"))
        self.assertEqual(find_user(users, "Base #2 North ok"), (BOB, "ok"))
        self.assertEqual(find_user(users, "(ridge base 1) meet at 5"), (ALICE, "meet at 5"))
        self.assertEqual(find_user(users, "(Base #2 North)ok"), (BOB, "ok"))
        self.assertEqual(find_user(users, "( Ridge Base 1 )"), (ALICE, ""))
        self.assertIsNone(find_user(users, "(Ridge) R1 hi"))  # in ( ), the whole name

    def test_shared_names(self):
        users = {ALICE: {"name": "Heltec V3"}, BOB: {"name": "heltec v3"}, ADMIN: {"name": "Heltec V3 Base"}}
        with self.assertRaisesRegex(AmbiguousUser, "^2 users are called Heltec V3; use the key prefix: "
                                                   "a1a1a1a1a1a1, b0b0b0b0b0b0$"):
            find_user(users, "Heltec V3 hi")
        with self.assertRaises(AmbiguousUser):
            find_user(users, "(heltec v3) hi")
        self.assertEqual(find_user(users, "Heltec V3 Base hi"), (ADMIN, "hi"))
        self.assertEqual(find_user(users, "b0b0 hi"), (BOB, "hi"))

    def test_unquote(self):
        self.assertEqual(unquote("(Sam T-Deck) hello"), ("Sam T-Deck", "hello"))
        self.assertIsNone(unquote("Sam hello"))
        self.assertIsNone(unquote("(Sam hello"))  # never closed

    def test_key_prefixes(self):
        self.assertEqual(find_user(self.USERS, "ADAD hello"), (ADMIN, "hello"))
        self.assertIsNone(find_user(self.USERS, "ada hello"))  # too short
        self.assertIsNone(find_user({ALICE: {}, "a1a1" + "00" * 30: {}}, "a1a1 hi"))  # not unique


class PossessiveTest(unittest.TestCase):
    def test_possessive(self):
        self.assertEqual(possessive("Alice"), "Alice's")
        self.assertEqual(possessive("fourbirds"), "fourbirds'")
        self.assertEqual(possessive("JAMES"), "JAMES'")


class RemoveUserTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.folder / "users.toml"
        self.path.write_text("# my notes\n" + USERS + f'\n# Bob next\n[users.{BOB}]\nname = "Bob"\n')
        self.directory = Directory(path=self.path)
        self.directory.load()

    def test_remove(self):
        self.assertEqual(self.directory.remove_user(ALICE), "removed Alice")
        self.assertEqual(set(self.directory.users), {BOB})
        text = self.path.read_text()
        self.assertNotIn(ALICE + "]", text)
        self.assertIn("# my notes", text)
        self.assertIn("# Bob next", text)
        self.assertEqual(parse_text(text), ({BOB: {"name": "Bob"}}, frozenset({ADMIN})))

    def test_remove_someone_not_there(self):
        before = self.path.read_text()
        self.assertEqual(self.directory.remove_user("cc" * 32), "no changes")
        self.assertEqual(self.path.read_text(), before)

    def test_in_memory(self):
        directory = Directory({ALICE: {"name": "Alice"}, BOB: {}})
        self.assertEqual(directory.remove_user(ALICE), "removed Alice")
        self.assertEqual(set(directory.users), {BOB})

if __name__ == "__main__":
    unittest.main()
