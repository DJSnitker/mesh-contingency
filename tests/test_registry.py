"""Mesh Contingency's commands as the registry finds them; the registry
itself is tested in packages/mesh-commands."""

import asyncio
import tomllib
import unittest
from pathlib import Path

from mesh_commands import KeyRoles, Sender
from mesh_commands.builtin.help import HelpCommand
from mesh_commands.registry import discover, resolve

from mesh_contingency.commands.alert import AlertCommand
from mesh_contingency.commands.testalert import TestAlertCommand
from mesh_contingency.config import ENTRY_POINT_GROUP, RETIRED_COMMANDS, load_commands

ADMIN_KEY = "ad" * 32
BUILT_IN = {"help": HelpCommand, "alert": AlertCommand, "testalert": TestAlertCommand}
ROOT = Path(__file__).resolve().parent.parent


def commands_config(**sections):
    return {"commands": sections}


class BuiltInTest(unittest.TestCase):
    def test_registered_as_entry_points(self):
        found = discover(ENTRY_POINT_GROUP)
        self.assertEqual(set(found), set(BUILT_IN))
        for name, cls in BUILT_IN.items():
            self.assertEqual(found[name], f"{cls.__module__}:{cls.__name__}")
            self.assertIs(resolve(found[name]), cls)

    def test_example_config_loads_every_built_in_command(self):
        with open(ROOT / "config.example.toml", "rb") as f:
            registry = load_commands(tomllib.load(f))
        self.assertEqual(set(registry.specs), set(BUILT_IN))
        self.assertEqual(registry.warnings, [])

    def test_built_and_answering(self):
        radio = object()
        state = object()
        registry = load_commands(commands_config(**{name: {"permission": "admin"} for name in BUILT_IN}))
        commands = registry.build(radio, KeyRoles(admins={ADMIN_KEY}), extras={"state": state})
        self.assertEqual({name: type(cmd) for name, cmd in commands.items()}, BUILT_IN)
        self.assertIs(commands["alert"].radio, radio)
        self.assertIs(commands["testalert"].ctx.extras["state"], state)
        reply = asyncio.run(commands["help"].execute("", Sender("Admin", ADMIN_KEY))).reply
        self.assertEqual(reply, "commands: help, alert, testalert. Send help <command> for usage")


class OldConfigTest(unittest.TestCase):
    def test_removed_commands_are_ignored_with_one_warning(self):
        r = load_commands(commands_config(alert={"permission": "admin"}, wx={"permission": "public"},
                                          msg={"permission": "user"}, quickim={"permission": "user"}))
        self.assertIn("alert", r.specs)
        self.assertEqual(r.warnings[0], "[commands] lists commands that no longer exist, ignored: wx, msg, quickim. "
                                        "Remove their entries.")
        self.assertTrue({"wx", "area", "verse", "rename"} <= RETIRED_COMMANDS)

    def test_old_email_caps_are_accepted(self):
        r = load_commands({"limits": {"emails_per_day": 50, "emails_per_day_total": 200}})
        self.assertEqual(r.limits.rates["public"], (10, 3600))

    def test_old_permissions_table_rejected(self):
        with self.assertRaisesRegex(SystemExit, r"\[permissions\] table is replaced"):
            load_commands({"permissions": {"alert": "public"}})


if __name__ == "__main__":
    unittest.main()
