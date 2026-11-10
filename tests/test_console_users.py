"""Console users: passwords, the console_users.json file and the
mesh-contingency-console user command. Console users are separate from
radio users, so none of this reads users.toml."""

import contextlib
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mesh_contingency.web import console_users as store
from mesh_contingency.web.launch import main

FAST_N = 2**10  # a cheap scrypt cost, for tests that don't check the default
GOOD = "correct horse battery"


class PasswordTest(unittest.TestCase):
    def test_hash_verifies_only_its_password(self):
        kept = store.hash_password(GOOD, FAST_N)
        self.assertTrue(store.verify_password(GOOD, kept))
        self.assertFalse(store.verify_password("correct horse batterY", kept))

    def test_default_cost_is_kept_with_the_hash(self):
        kept = store.hash_password(GOOD)
        self.assertEqual(kept.split("$")[:4], ["scrypt", str(2**15), "8", "1"])
        self.assertTrue(store.verify_password(GOOD, kept))

    def test_each_hash_has_its_own_salt(self):
        first, second = (store.hash_password("same password!", FAST_N) for _ in range(2))
        self.assertNotEqual(first, second)

    def test_a_broken_hash_never_verifies(self):
        for kept in ("", "plain text", "scrypt$3$8$1$c2FsdA==$aGFzaA==", "bcrypt$x", None):
            self.assertFalse(store.verify_password("anything at all", kept))

    def test_length_rules(self):
        self.assertIsNotNone(store.check_password("short"))
        self.assertIsNone(store.check_password("twelve chars"))
        self.assertIsNotNone(store.check_password("x" * 129))

    def test_name_rules(self):
        for good in ("sam", "eoc-1.desk", "a_b"):
            self.assertIsNone(store.check_name(good))
        for bad in ("", "-sam", "sam smith", "x" * 33):
            self.assertIsNotNone(store.check_name(bad))

    def test_names_are_compared_without_case(self):
        self.assertEqual(store.normal_name("  Sam.Jones "), "sam.jones")

    def test_a_new_password_is_always_a_change(self):
        user = store.new_user("sam", GOOD, n=FAST_N)
        before = user["changed"]
        store.set_password(user, "another password", n=FAST_N)
        self.assertGreater(user["changed"], before)
        self.assertTrue(store.verify_password("another password", user["password"]))


class FileTest(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(tempfile.TemporaryDirectory())) / store.USERS_FILE

    @staticmethod
    def user(name="sam"):
        return store.new_user(name, GOOD, n=FAST_N)

    def test_no_file_is_no_users(self):
        self.assertEqual(store.load(self.path), {})

    def test_saved_readable_only_by_owner_and_loaded_back(self):
        store.save(self.path, {"sam": self.user()})
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(store.load(self.path)["sam"]["created_by"], "node")
        self.assertFalse(self.path.with_name(self.path.name + ".tmp").exists())

    def test_the_password_itself_is_never_saved(self):
        store.save(self.path, {"sam": self.user()})
        self.assertNotIn(GOOD, self.path.read_text())

    def test_changing_saves_after_the_block(self):
        with store.changing(self.path) as users:
            users["sam"] = self.user()
        self.assertIn("sam", store.load(self.path))

    def test_changing_saves_nothing_if_the_block_fails(self):
        store.save(self.path, {"sam": self.user()})
        with self.assertRaises(SystemExit), store.changing(self.path) as users:
            del users["sam"]
            raise SystemExit("stop")
        self.assertIn("sam", store.load(self.path))

    def test_bad_files_say_why(self):
        good = self.user()
        cases = {
            "not json": "not valid JSON",
            "[]": "must be",
            json.dumps({"logins": []}): "must be",
            json.dumps({"users": [good, good]}): "two console users are called sam",
            json.dumps({"users": [{**good, "extra": 1}]}): "exactly",
            json.dumps({"users": [{**good, "admin": "a1" * 32}]}): "exactly",  # no tie to a radio
            json.dumps({"users": [{**good, "name": "Sam"}]}): "lowercase",
            json.dumps({"users": [{**good, "password": "hunter2"}]}): "user password",
            json.dumps({"users": [{**good, "created_by": ""}]}): "created_by",
            json.dumps({"users": [{**good, "changed": True}]}): "changed",
        }
        for text, error in cases.items():
            self.path.write_text(text)
            with self.subTest(text=text[:40]), self.assertRaisesRegex(store.ConsoleUsersError, error):
                store.load(self.path)


class CommandTest(unittest.TestCase):
    """mesh-contingency-console user ..., with typed passwords."""

    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.config = self.folder / "config.toml"
        self.config.write_text("")  # no users.toml: console users don't need one
        self.path = self.folder / store.USERS_FILE
        self.passwords = []
        self.enterContext(mock.patch("getpass.getpass", side_effect=lambda prompt: self.next_password()))
        self.enterContext(mock.patch.object(store, "SCRYPT_N", FAST_N))
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))

    def next_password(self):
        if not self.passwords:
            raise EOFError
        return self.passwords.pop(0)

    def run_user(self, *words):
        return main(["-c", str(self.config), "user", *words])

    def fails(self, pattern, *words):
        with self.assertRaisesRegex(SystemExit, pattern):
            self.run_user(*words)

    def add(self, name="sam", password=GOOD):
        self.passwords += [password, password]
        self.run_user("add", name)

    def test_add(self):
        self.add()
        user = store.load(self.path)["sam"]
        self.assertTrue(store.verify_password(GOOD, user["password"]))
        self.assertEqual(user["created_by"], "node")
        self.assertIn("Added console user sam", self.out.getvalue())
        self.assertNotIn(GOOD, self.out.getvalue())

    def test_name_is_lowered(self):
        self.add("Sam")
        self.assertEqual(list(store.load(self.path)), ["sam"])
        self.fails("already a console user called sam", "add", "SAM")

    def test_bad_name(self):
        self.fails("letters, digits", "add", "sam smith")
        self.assertFalse(self.path.exists())

    def test_short_or_mismatched_passwords_are_asked_again(self):
        self.passwords += ["short", GOOD, "something else!", GOOD, GOOD]
        self.run_user("add", "sam")
        self.assertIn("12 to 128 characters", self.out.getvalue())
        self.assertIn("don't match", self.out.getvalue())
        self.assertIn("sam", store.load(self.path))

    def test_stopping_changes_nothing(self):
        self.passwords.append(GOOD)  # then Ctrl+D
        self.fails("Stopped: nothing changed", "add", "sam")
        self.assertFalse(self.path.exists())

    def test_new_password(self):
        self.add()
        self.passwords += ["a whole new password"] * 2
        self.run_user("password", "Sam")
        user = store.load(self.path)["sam"]
        self.assertTrue(store.verify_password("a whole new password", user["password"]))
        self.assertFalse(store.verify_password(GOOD, user["password"]))

    def test_remove(self):
        self.add()
        self.add("alex")
        self.run_user("remove", "sam")
        self.assertEqual(list(store.load(self.path)), ["alex"])
        self.fails("No console user called sam", "remove", "sam")
        self.fails("No console user called sam", "password", "sam")

    def test_the_last_one_can_be_removed_here(self):
        # The browser won't remove the last one; the node's own command can.
        self.add()
        self.run_user("remove", "sam")
        self.assertEqual(store.load(self.path), {})

    def test_list(self):
        self.run_user("list")
        self.assertIn("No console users yet", self.out.getvalue())
        self.add()
        with store.changing(self.path) as users:
            users["alex"] = store.new_user("alex", GOOD, created_by="sam")
        self.run_user("list")
        self.assertRegex(self.out.getvalue(), r"alex +made \d{4}-\d\d-\d\d by sam, password set")
        self.assertRegex(self.out.getvalue(), r"sam +made \d{4}-\d\d-\d\d on the node")

    def test_a_bad_file_is_named(self):
        self.path.write_text("{")
        self.fails(f"{store.USERS_FILE}: not valid JSON", "list")

    def test_works_with_the_console_off(self):
        # Made before the console is turned on, so it's ready when it is.
        self.config.write_text("[console]\nenabled = false\n")
        self.add()
        self.assertIn("sam", store.load(self.path))
