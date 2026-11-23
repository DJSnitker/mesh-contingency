import tomllib
import unittest
from importlib.metadata import EntryPoint
from pathlib import Path
from unittest import mock

from mesh_contingency.api import (
    ADMIN,
    DEFAULT_TIMEOUT,
    DISABLED,
    PUBLIC,
    USER,
    Command,
    CommandResult,
    FunctionCommand,
    Sender,
)
from mesh_contingency.commands.alert import AlertCommand
from mesh_contingency.commands.help import HelpCommand
from mesh_contingency.commands.testalert import TestAlertCommand
from mesh_contingency.registry import ENTRY_POINT_GROUP, RETIRED, Registry, discover, resolve

ADMIN_KEY = "ad" * 32
DANA = Sender("Dana", "d0" * 32)
BUILT_IN = {"help": HelpCommand, "alert": AlertCommand, "testalert": TestAlertCommand}


# Handlers used by the tests below, named as "tests.test_registry:<attr>".
class EchoCommand(Command):
    args = "<text>"

    async def execute(self, text, sender):
        return CommandResult(console=text, reply=f"{self.ctx.options.get('prefix', '')}{text}")


def shout(text, sender, ctx):
    """Repeat the text in capitals."""
    return text.upper()


class Broken(Command):
    def __init__(self, ctx):
        raise RuntimeError("no radio")

    async def execute(self, text, sender):
        pass  # pragma: no cover


class NotACommand:
    pass


NOT_CALLABLE = 42


def commands_config(**sections):
    return {"commands": sections}


class DiscoverTest(unittest.TestCase):
    def test_built_in_commands_registered_as_entry_points(self):
        found = discover()
        for name, cls in BUILT_IN.items():
            self.assertEqual(found[name], f"{cls.__module__}:{cls.__name__}")
            self.assertIs(resolve(found[name]), cls)

    def patch_entry_points(self, *pairs):
        eps = [EntryPoint(name, value, ENTRY_POINT_GROUP) for name, value in pairs]
        return mock.patch("mesh_contingency.registry.entry_points", return_value=eps)

    def test_same_name_same_code_is_fine(self):
        # e.g. stale metadata from an old install of the same package
        with self.patch_entry_points(("wx", "a:B"), ("wx", "a:B")):
            self.assertEqual(discover(), {"wx": "a:B"})

    def test_conflicting_packages_stop_startup(self):
        with self.patch_entry_points(("wx", "a:B"), ("wx", "c:D")):
            with self.assertRaisesRegex(SystemExit, "Two installed packages provide the command 'wx': a:B and c:D"):
                discover()


class ResolveTest(unittest.TestCase):
    def test_class_and_function(self):
        self.assertIs(resolve("tests.test_registry:EchoCommand"), EchoCommand)
        self.assertIs(resolve("tests.test_registry:shout"), shout)
        self.assertIs(resolve("mesh_contingency.api:Command.split_reply"), Command.split_reply)

    def test_rejects_other_objects(self):
        with self.assertRaisesRegex(TypeError, "not a Command subclass$"):
            resolve("tests.test_registry:NotACommand")
        with self.assertRaisesRegex(TypeError, "not a Command subclass or function"):
            resolve("tests.test_registry:NOT_CALLABLE")

    def test_import_errors_propagate(self):
        with self.assertRaises(ModuleNotFoundError):
            resolve("no_such_module_xyz:thing")
        with self.assertRaises(AttributeError):
            resolve("tests.test_registry:missing")


class RegistryConfigTest(unittest.TestCase):
    AVAILABLE = {"alert": "mesh_contingency.commands.alert:AlertCommand",
                 "testalert": "mesh_contingency.commands.testalert:TestAlertCommand"}

    def registry(self, config):
        return Registry(config, available=self.AVAILABLE)

    def test_enabled_disabled_and_missing(self):
        r = self.registry(commands_config(alert={"permission": "public"}, testalert={"permission": "disabled"}))
        self.assertEqual(list(r.specs), ["alert"])
        self.assertEqual(r.specs["alert"].permission, PUBLIC)
        self.assertEqual(r.specs["alert"].timeout, DEFAULT_TIMEOUT)
        self.assertEqual(r.disabled, ["testalert"])
        self.assertEqual(r.warnings, [])
        self.assertIs(r.factories["alert"], AlertCommand)
        self.assertNotIn("testalert", r.factories)  # disabled code is never imported

    def test_installed_command_without_section_is_disabled_with_warning(self):
        r = self.registry(commands_config(alert={"permission": "public"}))
        self.assertEqual(r.disabled, ["testalert"])
        self.assertEqual(r.warnings, ["testalert has no [commands.testalert] section; disabled."])

    def test_no_commands_section(self):
        r = self.registry({})
        self.assertEqual(r.specs, {})
        self.assertEqual(r.disabled, ["alert", "testalert"])

    def test_options_timeout_and_handler(self):
        r = self.registry(commands_config(
            echo={"permission": "user", "handler": "tests.test_registry:EchoCommand", "timeout": 2.5,
                  "prefix": ">", "limit": 3}))
        spec = r.specs["echo"]
        self.assertEqual((spec.permission, spec.timeout), (USER, 2.5))
        self.assertEqual(spec.options, {"prefix": ">", "limit": 3})
        self.assertIs(r.factories["echo"], EchoCommand)

    def test_handler_overrides_installed_command(self):
        r = self.registry(commands_config(alert={"permission": "public", "handler": "tests.test_registry:shout"}))
        self.assertIs(r.factories["alert"], shout)

    def test_old_permissions_table_rejected(self):
        with self.assertRaisesRegex(SystemExit, r"\[permissions\] table is replaced"):
            self.registry({"permissions": {"alert": "public"}})

    def test_config_mistakes_stop_startup(self):
        cases = [
            (commands_config(alertx={"permission": "public"}),
             r"Unknown command 'alertx' in \[commands\]; installed commands are: alert, testalert"),
            (commands_config(Alert={"permission": "public"}), "Bad command name 'Alert'"),
            (commands_config(**{"my-cmd": {"permission": "public"}}), "Bad command name 'my-cmd'"),
            (commands_config(alert="public"), r"\[commands.alert\] must be a table"),
            (commands_config(alert={}),
             r"\[commands.alert\] needs a permission; use one of: public, user, admin, disabled"),
            (commands_config(alert={"permission": "everyone"}), "has unknown permission 'everyone'"),
            (commands_config(alert={"permission": "Public"}), "has unknown permission 'Public'"),
            (commands_config(x={"permission": "public", "handler": "no colon"}), "handler must look like"),
            (commands_config(x={"permission": "public", "handler": 5}), "handler must look like"),
            (commands_config(alert={"permission": "public", "timeout": 0}), "timeout must be a positive number"),
            (commands_config(alert={"permission": "public", "timeout": "5"}), "timeout must be a positive number"),
            (commands_config(alert={"permission": "public", "timeout": True}), "timeout must be a positive number"),
        ]
        for config, message in cases:
            with self.subTest(config=config), self.assertRaisesRegex(SystemExit, message):
                self.registry(config)

    def test_disabled_command_still_checked(self):
        with self.assertRaisesRegex(SystemExit, "Unknown command 'nope'"):
            self.registry(commands_config(nope={"permission": "disabled"}))

    def test_import_failure_skipped_with_warning(self):
        r = self.registry(commands_config(
            alert={"permission": "public"},
            gone={"permission": "public", "handler": "no_such_module_xyz:thing"},
            odd={"permission": "public", "handler": "tests.test_registry:NotACommand"}))
        self.assertEqual(list(r.specs), ["alert"])
        load_warnings = [w for w in r.warnings if w.startswith("Could not load")]
        self.assertTrue(load_warnings[0].startswith("Could not load gone (no_such_module_xyz:thing): "))
        self.assertIn("not a Command subclass; skipped.", load_warnings[1])

    def test_discovers_by_default(self):
        r = Registry(commands_config(alert={"permission": "admin"}))
        self.assertEqual(set(r.disabled), set(BUILT_IN) - {"alert"})

    def test_removed_commands_are_ignored_with_one_warning(self):
        r = self.registry(commands_config(alert={"permission": "admin"}, wx={"permission": "public"},
                                          msg={"permission": "user"}, quickim={"permission": "user"}))
        self.assertEqual(list(r.specs), ["alert"])
        self.assertEqual(r.warnings[0], "[commands] lists commands that no longer exist, ignored: wx, msg, quickim. "
                                        "Remove their entries (see config.example.toml).")
        self.assertNotIn("wx", r.disabled)

    def test_a_removed_name_with_a_handler_is_your_own_command(self):
        r = self.registry(commands_config(wx={"permission": "public", "handler": "tests.test_registry:shout"}))
        self.assertIs(r.factories["wx"], shout)
        self.assertFalse(any("no longer exist" in w for w in r.warnings))
        self.assertIn("wx", RETIRED)


class ExampleConfigTest(unittest.TestCase):
    def test_example_config_loads_every_built_in_command(self):
        with open(Path(__file__).resolve().parent.parent / "config.example.toml", "rb") as f:
            registry = Registry(tomllib.load(f))
        self.assertEqual(set(registry.specs), set(BUILT_IN))
        self.assertEqual(registry.warnings, [])


class RegistryBuildTest(unittest.TestCase):
    def test_built_in_commands(self):
        radio = object()
        sections = {name: {"permission": level} for name, level in [
            ("help", "admin"), ("alert", "admin"), ("testalert", "admin")]}
        commands = Registry(commands_config(**sections)).build({ADMIN_KEY}, radio)
        self.assertEqual(list(commands), list(sections))
        for name, cmd in commands.items():
            self.assertIs(type(cmd), BUILT_IN[name])
            self.assertEqual(cmd.name, name)
            self.assertEqual(cmd.permission, sections[name]["permission"])
        self.assertIs(commands["alert"].radio, radio)
        self.assertIs(commands["help"].ctx.commands, commands)  # help sees every command
        self.assertEqual(commands["help"].ctx.admins, {ADMIN_KEY})

    def test_context_and_settings(self):
        r = Registry(commands_config(
            echo={"permission": "admin", "handler": "tests.test_registry:EchoCommand", "timeout": 5, "prefix": ">"}),
            available={})
        radio = object()
        cmd = r.build({ADMIN_KEY}, radio)["echo"]
        self.assertEqual((cmd.name, cmd.permission, cmd.timeout, cmd.usage), ("echo", ADMIN, 5, "echo <text>"))
        ctx = cmd.ctx
        self.assertEqual((ctx.name, ctx.options), ("echo", {"prefix": ">"}))
        self.assertEqual((ctx.users, ctx.admins), ({}, {ADMIN_KEY}))
        self.assertIs(ctx.radio, radio)
        self.assertFalse(ctx.allowed(cmd, DANA))
        self.assertTrue(ctx.allowed(cmd, Sender("Admin", ADMIN_KEY)))

    def test_permission_and_timeout_are_per_instance(self):
        Registry(commands_config(alert={"permission": "admin", "timeout": 3})).build(set(), None)
        self.assertEqual(AlertCommand.permission, DISABLED)
        self.assertEqual(AlertCommand.timeout, DEFAULT_TIMEOUT)

    def test_same_code_under_two_names(self):
        # e.g. a second alert command posting somewhere else
        r = Registry(commands_config(
            alert={"permission": "admin"},
            alert_storm={"permission": "admin", "handler": "mesh_contingency.commands.alert:AlertCommand",
                         "channel": "#storm-watch"}))
        commands = r.build(set(), None)
        self.assertEqual(commands["alert_storm"].channel, "#storm-watch")
        self.assertEqual(commands["alert_storm"].usage, "alert_storm <message>")

    def test_function_command_wrapped(self):
        r = Registry(commands_config(shout={"permission": "public", "handler": "tests.test_registry:shout"}),
                     available={})
        cmd = r.build(set(), None)["shout"]
        self.assertIsInstance(cmd, FunctionCommand)
        self.assertEqual(cmd.summary, "Repeat the text in capitals.")

    def test_command_that_fails_to_start_is_skipped(self):
        r = Registry(commands_config(
            broken={"permission": "public", "handler": "tests.test_registry:Broken"},
            shout={"permission": "public", "handler": "tests.test_registry:shout"}), available={})
        self.assertEqual(list(r.build(set(), None)), ["shout"])
        self.assertEqual(r.warnings, ["Could not start broken: no radio; skipped."])


if __name__ == "__main__":
    unittest.main()
