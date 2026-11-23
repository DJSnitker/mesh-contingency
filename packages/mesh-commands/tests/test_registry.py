import unittest
from importlib.metadata import EntryPoint
from unittest import mock

from mesh_commands import (
    ADMIN,
    DEFAULT_TIMEOUT,
    DISABLED,
    PUBLIC,
    USER,
    Command,
    CommandResult,
    FunctionCommand,
    KeyRoles,
    Sender,
)
from mesh_commands.builtin.help import HelpCommand
from mesh_commands.registry import Registry, discover, resolve

ADMIN_KEY = "ad" * 32
DANA = Sender("Dana", "d0" * 32)
GROUP = "tests.commands"
ROLES = KeyRoles(admins={ADMIN_KEY})


# Handlers used by the tests below, named as "tests.test_registry:<attr>".
class EchoCommand(Command):
    args = "<text>"

    async def execute(self, text, sender):
        return CommandResult(console=text, reply=f"{self.ctx.options.get('prefix', '')}{text}")


def shout(text, sender, ctx):
    """Repeat the text in capitals."""
    return text.upper()


class PostCommand(Command):
    """Like a project's own command, with an option of its own."""

    args = "<message>"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.channel = ctx.options.get("channel", "#default")

    async def execute(self, text, sender):
        return f"posted to {self.channel}"


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
    def patch_entry_points(self, *pairs):
        eps = [EntryPoint(name, value, GROUP) for name, value in pairs]
        return mock.patch("mesh_commands.registry.entry_points", return_value=eps)

    def test_finds_the_groups_commands(self):
        with self.patch_entry_points(("help", "mesh_commands.builtin.help:HelpCommand")) as found:
            self.assertEqual(discover(GROUP), {"help": "mesh_commands.builtin.help:HelpCommand"})
        found.assert_called_once_with(group=GROUP)

    def test_same_name_same_code_is_fine(self):
        # e.g. stale metadata from an old install of the same package
        with self.patch_entry_points(("wx", "a:B"), ("wx", "a:B")):
            self.assertEqual(discover(GROUP), {"wx": "a:B"})

    def test_conflicting_packages_stop_startup(self):
        with self.patch_entry_points(("wx", "a:B"), ("wx", "c:D")):
            with self.assertRaisesRegex(SystemExit, "Two installed packages provide the command 'wx': a:B and c:D"):
                discover(GROUP)

    def test_registry_discovers_from_its_group(self):
        with self.patch_entry_points(("help", "mesh_commands.builtin.help:HelpCommand"), ("post", "x:Y")):
            r = Registry({"commands": {"help": {"permission": "public"}}}, GROUP)
        self.assertIs(r.factories["help"], HelpCommand)
        self.assertEqual(r.disabled, ["post"])

    def test_no_group_means_only_handlers(self):
        r = Registry({"commands": {"shout": {"permission": "public", "handler": "tests.test_registry:shout"}}})
        self.assertEqual(list(r.specs), ["shout"])
        self.assertEqual(r.disabled, [])


class ResolveTest(unittest.TestCase):
    def test_class_and_function(self):
        self.assertIs(resolve("tests.test_registry:EchoCommand"), EchoCommand)
        self.assertIs(resolve("tests.test_registry:shout"), shout)
        self.assertIs(resolve("mesh_commands.command:Command.split_reply"), Command.split_reply)

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
    AVAILABLE = {"alert": "tests.test_registry:PostCommand", "testalert": "tests.test_registry:EchoCommand"}

    def registry(self, config):
        return Registry(config, available=self.AVAILABLE)

    def test_enabled_disabled_and_missing(self):
        r = self.registry(commands_config(alert={"permission": "public"}, testalert={"permission": "disabled"}))
        self.assertEqual(list(r.specs), ["alert"])
        self.assertEqual(r.specs["alert"].permission, PUBLIC)
        self.assertEqual(r.specs["alert"].timeout, DEFAULT_TIMEOUT)
        self.assertEqual(r.disabled, ["testalert"])
        self.assertEqual(r.warnings, [])
        self.assertIs(r.factories["alert"], PostCommand)
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

    def test_retired_commands_are_ignored_with_one_warning(self):
        r = Registry(commands_config(alert={"permission": "admin"}, wx={"permission": "public"},
                                     msg={"permission": "user"}), available=self.AVAILABLE, retired={"wx", "msg"})
        self.assertEqual(list(r.specs), ["alert"])
        self.assertEqual(r.warnings[0], "[commands] lists commands that no longer exist, ignored: wx, msg. "
                                        "Remove their entries.")
        self.assertNotIn("wx", r.disabled)

    def test_a_retired_name_with_a_handler_is_your_own_command(self):
        r = Registry(commands_config(wx={"permission": "public", "handler": "tests.test_registry:shout"}),
                     available={}, retired={"wx"})
        self.assertIs(r.factories["wx"], shout)
        self.assertFalse(any("no longer exist" in w for w in r.warnings))

    def test_without_retired_names_they_are_unknown(self):
        with self.assertRaisesRegex(SystemExit, "Unknown command 'wx'"):
            Registry(commands_config(wx={"permission": "public"}), available={})


class RegistryBuildTest(unittest.TestCase):
    AVAILABLE = {"help": "mesh_commands.builtin.help:HelpCommand", "post": "tests.test_registry:PostCommand"}

    def test_commands_share_the_context(self):
        radio = object()
        extras = {"state": object()}
        sent = []
        r = Registry(commands_config(help={"permission": "public"}, post={"permission": "admin", "timeout": 5}),
                     available=self.AVAILABLE)
        commands = r.build(radio, ROLES, send=lambda key, text: sent.append((key, text)), extras=extras)
        self.assertEqual(list(commands), ["help", "post"])
        help_, post = commands["help"], commands["post"]
        self.assertIsInstance(help_, HelpCommand)
        self.assertEqual((post.name, post.permission, post.timeout, post.usage), ("post", ADMIN, 5, "post <message>"))
        self.assertIs(help_.ctx.commands, commands)  # help sees every command
        for cmd in commands.values():
            self.assertIs(cmd.ctx.radio, radio)
            self.assertIs(cmd.ctx.roles, ROLES)
            self.assertIs(cmd.ctx.extras, extras)
        post.ctx.send("k", "hi")
        self.assertEqual(sent, [("k", "hi")])
        self.assertFalse(post.ctx.allowed(post, DANA))
        self.assertTrue(post.ctx.allowed(post, Sender("Admin", ADMIN_KEY)))

    def test_options(self):
        r = Registry(commands_config(
            echo={"permission": "admin", "handler": "tests.test_registry:EchoCommand", "prefix": ">"}), available={})
        ctx = r.build()["echo"].ctx
        self.assertEqual((ctx.name, ctx.options, ctx.extras), ("echo", {"prefix": ">"}, {}))
        self.assertFalse(ctx.roles.is_admin(ADMIN_KEY))  # no roles given: nobody

    def test_permission_and_timeout_are_per_instance(self):
        Registry(commands_config(post={"permission": "admin", "timeout": 3}), available=self.AVAILABLE).build()
        self.assertEqual(PostCommand.permission, DISABLED)
        self.assertEqual(PostCommand.timeout, DEFAULT_TIMEOUT)

    def test_same_code_under_two_names(self):
        # e.g. a second command posting somewhere else
        r = Registry(commands_config(
            post={"permission": "admin"},
            post_storm={"permission": "admin", "handler": "tests.test_registry:PostCommand", "channel": "#storm"}),
            available=self.AVAILABLE)
        commands = r.build()
        self.assertEqual(commands["post_storm"].channel, "#storm")
        self.assertEqual(commands["post_storm"].usage, "post_storm <message>")

    def test_function_command_wrapped(self):
        r = Registry(commands_config(shout={"permission": "public", "handler": "tests.test_registry:shout"}),
                     available={})
        cmd = r.build()["shout"]
        self.assertIsInstance(cmd, FunctionCommand)
        self.assertEqual(cmd.summary, "Repeat the text in capitals.")

    def test_command_that_fails_to_start_is_skipped(self):
        r = Registry(commands_config(
            broken={"permission": "public", "handler": "tests.test_registry:Broken"},
            shout={"permission": "public", "handler": "tests.test_registry:shout"}), available={})
        self.assertEqual(list(r.build()), ["shout"])
        self.assertEqual(r.warnings, ["Could not start broken: no radio; skipped."])

if __name__ == "__main__":
    unittest.main()
