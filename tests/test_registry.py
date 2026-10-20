import unittest

from commands import ADMIN, PUBLIC, USER, build_commands, load_admins, load_users
from commands.advert import AdvertCommand
from commands.notify_default import NotifyDefaultCommand
from commands.notify_email import NotifyEmailCommand
from commands.notify_group import NotifyGroupCommand
from commands.verse import VerseCommand
from commands.wx import WxCommand

FULL_KEY = "D0D0D0D0D0D0" + "ab" * 26


class LoadUsersTest(unittest.TestCase):
    def test_keys_normalized_to_lowercase_prefix(self):
        users = load_users({"users": {FULL_KEY: {"notify_default": "a@example.com"},
                                      " B0B0B0B0B0B0 ": {}}})
        self.assertEqual(users, {"d0d0d0d0d0d0": {"notify_default": "a@example.com"}, "b0b0b0b0b0b0": {}})

    def test_missing_section(self):
        self.assertEqual(load_users({}), {})


class LoadAdminsTest(unittest.TestCase):
    def test_keys_normalized(self):
        self.assertEqual(load_admins({"admin": {"keys": [FULL_KEY, "adadadadadad"]}}),
                         {"d0d0d0d0d0d0", "adadadadadad"})

    def test_missing_section(self):
        self.assertEqual(load_admins({}), set())
        self.assertEqual(load_admins({"admin": {}}), set())


class BuildCommandsTest(unittest.TestCase):
    def test_registry(self):
        radio = object()
        commands = build_commands({"users": {FULL_KEY: {"notify_default": "a@example.com"}}}, radio)
        expected = {"wx": (WxCommand, PUBLIC), "verse": (VerseCommand, PUBLIC),
                    "notify_default": (NotifyDefaultCommand, USER),
                    "notify_group": (NotifyGroupCommand, USER), "notify_email": (NotifyEmailCommand, USER),
                    "advert": (AdvertCommand, ADMIN)}
        self.assertEqual(set(commands), set(expected))
        for name, (cls, permission) in expected.items():
            self.assertIs(type(commands[name]), cls)
            self.assertEqual(commands[name].name, name)
            self.assertEqual(commands[name].permission, permission)
        self.assertIs(commands["advert"].radio, radio)
        self.assertEqual(commands["notify_default"].recipients, {"d0d0d0d0d0d0": ["a@example.com"]})

    def test_names_are_lowercase(self):
        for name in build_commands({}, None):
            self.assertEqual(name, name.lower())


if __name__ == "__main__":
    unittest.main()
