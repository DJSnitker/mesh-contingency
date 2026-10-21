import sys
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
from mesh_contingency.commands.advert import AdvertCommand
from mesh_contingency.commands.alert import AlertCommand
from mesh_contingency.commands.contacts import ContactsCommand
from mesh_contingency.commands.email import EmailCommand
from mesh_contingency.commands.emailall import EmailAllCommand
from mesh_contingency.commands.health import HealthCommand
from mesh_contingency.commands.help import HelpCommand
from mesh_contingency.commands.history import HistoryCommand
from mesh_contingency.commands.join import ApproveCommand, DenyCommand, JoinCommand
from mesh_contingency.commands.mailbox import ClearInboxCommand, InboxCommand, MsgCommand, SetPassCommand
from mesh_contingency.commands.quickim import QuickImCommand
from mesh_contingency.commands.reload import ReloadCommand
from mesh_contingency.commands.roster import RosterCommand
from mesh_contingency.commands.settings import AddGroupCommand, ClearGroupCommand, SetQuickImCommand
from mesh_contingency.commands.status import ClearStatusCommand, OkCommand, StatusCommand
from mesh_contingency.commands.users import (
    LeaveCommand,
    RemoveCommand,
    ResetPassCommand,
    UsersCommand,
    WhoAmICommand,
    WhoisCommand,
)
from mesh_contingency.commands.verse import VerseCommand
from mesh_contingency.commands.wx import WxCommand
from mesh_contingency.directory import Directory
from mesh_contingency.registry import ENTRY_POINT_GROUP, Registry, discover, resolve

FULL_KEY = "D0D0D0D0D0D0" + "ab" * 26
DANA = Sender("Dana", "d0" * 32)
BUILT_IN = {"help": HelpCommand, "wx": WxCommand, "verse": VerseCommand,
            "quickim": QuickImCommand, "emailall": EmailAllCommand,
            "email": EmailCommand, "advert": AdvertCommand, "contacts": ContactsCommand, "reload": ReloadCommand,
            "ok": OkCommand, "status": StatusCommand, "clearstatus": ClearStatusCommand,
            "roster": RosterCommand, "health": HealthCommand, "history": HistoryCommand,
            "msg": MsgCommand, "inbox": InboxCommand,
            "clearinbox": ClearInboxCommand, "setpass": SetPassCommand, "alert": AlertCommand,
            "join": JoinCommand, "approve": ApproveCommand, "deny": DenyCommand, "setquickim": SetQuickImCommand,
            "addgroup": AddGroupCommand, "cleargroup": ClearGroupCommand, "users": UsersCommand,
            "whois": WhoisCommand, "remove": RemoveCommand, "resetpass": ResetPassCommand,
            "whoami": WhoAmICommand, "leave": LeaveCommand}
EXAMPLE_PLUGIN = Path(__file__).resolve().parent.parent / "examples" / "mesh-dice"


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
    AVAILABLE = {"wx": "mesh_contingency.commands.wx:WxCommand",
                 "advert": "mesh_contingency.commands.advert:AdvertCommand"}

    def registry(self, config):
        return Registry(config, available=self.AVAILABLE)

    def test_enabled_disabled_and_missing(self):
        r = self.registry(commands_config(wx={"permission": "public"}, advert={"permission": "disabled"}))
        self.assertEqual(list(r.specs), ["wx"])
        self.assertEqual(r.specs["wx"].permission, PUBLIC)
        self.assertEqual(r.specs["wx"].timeout, DEFAULT_TIMEOUT)
        self.assertEqual(r.disabled, ["advert"])
        self.assertEqual(r.warnings, [])
        self.assertIs(r.factories["wx"], WxCommand)
        self.assertNotIn("advert", r.factories)  # disabled code is never imported

    def test_installed_command_without_section_is_disabled_with_warning(self):
        r = self.registry(commands_config(wx={"permission": "public"}))
        self.assertEqual(r.disabled, ["advert"])
        self.assertEqual(r.warnings, ["advert has no [commands.advert] section; disabled."])

    def test_no_commands_section(self):
        r = self.registry({})
        self.assertEqual(r.specs, {})
        self.assertEqual(r.disabled, ["wx", "advert"])

    def test_options_timeout_and_handler(self):
        r = self.registry(commands_config(
            echo={"permission": "user", "handler": "tests.test_registry:EchoCommand", "timeout": 2.5,
                  "prefix": ">", "limit": 3}))
        spec = r.specs["echo"]
        self.assertEqual((spec.permission, spec.timeout), (USER, 2.5))
        self.assertEqual(spec.options, {"prefix": ">", "limit": 3})
        self.assertIs(r.factories["echo"], EchoCommand)

    def test_handler_overrides_installed_command(self):
        r = self.registry(commands_config(wx={"permission": "public", "handler": "tests.test_registry:shout"}))
        self.assertIs(r.factories["wx"], shout)

    def test_old_permissions_table_rejected(self):
        with self.assertRaisesRegex(SystemExit, r"\[permissions\] table is replaced"):
            self.registry({"permissions": {"wx": "public"}})

    def test_config_mistakes_stop_startup(self):
        cases = [
            (commands_config(wxx={"permission": "public"}),
             r"Unknown command 'wxx' in \[commands\]; installed commands are: wx, advert"),
            (commands_config(Wx={"permission": "public"}), "Bad command name 'Wx'"),
            (commands_config(**{"my-cmd": {"permission": "public"}}), "Bad command name 'my-cmd'"),
            (commands_config(wx="public"), r"\[commands.wx\] must be a table"),
            (commands_config(wx={}), r"\[commands.wx\] needs a permission; use one of: public, user, admin, disabled"),
            (commands_config(wx={"permission": "everyone"}), "has unknown permission 'everyone'"),
            (commands_config(wx={"permission": "Public"}), "has unknown permission 'Public'"),
            (commands_config(x={"permission": "public", "handler": "no colon"}), "handler must look like"),
            (commands_config(x={"permission": "public", "handler": 5}), "handler must look like"),
            (commands_config(wx={"permission": "public", "timeout": 0}), "timeout must be a positive number"),
            (commands_config(wx={"permission": "public", "timeout": "5"}), "timeout must be a positive number"),
            (commands_config(wx={"permission": "public", "timeout": True}), "timeout must be a positive number"),
        ]
        for config, message in cases:
            with self.subTest(config=config), self.assertRaisesRegex(SystemExit, message):
                self.registry(config)

    def test_disabled_command_still_checked(self):
        with self.assertRaisesRegex(SystemExit, "Unknown command 'nope'"):
            self.registry(commands_config(nope={"permission": "disabled"}))

    def test_import_failure_skipped_with_warning(self):
        r = self.registry(commands_config(
            wx={"permission": "public"},
            gone={"permission": "public", "handler": "no_such_module_xyz:thing"},
            odd={"permission": "public", "handler": "tests.test_registry:NotACommand"}))
        self.assertEqual(list(r.specs), ["wx"])
        load_warnings = [w for w in r.warnings if w.startswith("Could not load")]
        self.assertTrue(load_warnings[0].startswith("Could not load gone (no_such_module_xyz:thing): "))
        self.assertIn("not a Command subclass; skipped.", load_warnings[1])

    def test_discovers_by_default(self):
        r = Registry(commands_config(wx={"permission": "public"}))
        self.assertEqual(set(r.disabled), set(BUILT_IN) - {"wx"})


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
            ("help", "public"), ("wx", "public"), ("verse", "public"), ("quickim", "user"),
            ("emailall", "user"), ("email", "user"), ("advert", "admin"), ("reload", "admin")]}
        directory = Directory({FULL_KEY.lower(): {"quickim": "a@example.com"}})
        commands = Registry(commands_config(**sections)).build(directory, radio)
        self.assertEqual(list(commands), list(sections))
        for name, cmd in commands.items():
            self.assertIs(type(cmd), BUILT_IN[name])
            self.assertEqual(cmd.name, name)
            self.assertEqual(cmd.permission, sections[name]["permission"])
        self.assertIs(commands["advert"].radio, radio)
        self.assertEqual(commands["quickim"].recipients, {FULL_KEY.lower(): ["a@example.com"]})
        self.assertIs(commands["help"].ctx.commands, commands)  # help sees every command

    def test_context_and_settings(self):
        r = Registry(commands_config(
            echo={"permission": "admin", "handler": "tests.test_registry:EchoCommand", "timeout": 5, "prefix": ">"}),
            available={})
        directory, radio = Directory({"d0" * 32: {}}, {"ad" * 32}), object()
        cmd = r.build(directory, radio)["echo"]
        self.assertEqual((cmd.name, cmd.permission, cmd.timeout, cmd.usage), ("echo", ADMIN, 5, "echo <text>"))
        ctx = cmd.ctx
        self.assertEqual((ctx.name, ctx.options), ("echo", {"prefix": ">"}))
        self.assertIs(ctx.directory, directory)
        self.assertEqual((ctx.users, ctx.admins), ({"d0" * 32: {}}, {"ad" * 32}))
        self.assertIs(ctx.radio, radio)
        self.assertFalse(ctx.allowed(cmd, DANA))

    def test_permission_and_timeout_are_per_instance(self):
        Registry(commands_config(wx={"permission": "public", "timeout": 3})).build(Directory(), None)
        self.assertEqual(WxCommand.permission, DISABLED)
        self.assertEqual(WxCommand.timeout, DEFAULT_TIMEOUT)

    def test_same_code_under_two_names(self):
        # e.g. a second quickim command with its own per-user addresses
        r = Registry(commands_config(
            quickim={"permission": "user"},
            quickim_mom={"permission": "user", "handler": "mesh_contingency.commands.quickim:QuickImCommand"}))
        users = {"d0" * 32: {"quickim": "a@example.com", "quickim_mom": "mom@example.com"}}
        commands = r.build(Directory(users), None)
        self.assertEqual(commands["quickim_mom"].recipients, {"d0" * 32: ["mom@example.com"]})
        self.assertEqual(commands["quickim_mom"].usage, "quickim_mom <message>")

    def test_function_command_wrapped(self):
        r = Registry(commands_config(shout={"permission": "public", "handler": "tests.test_registry:shout"}),
                     available={})
        cmd = r.build(Directory(), None)["shout"]
        self.assertIsInstance(cmd, FunctionCommand)
        self.assertEqual(cmd.summary, "Repeat the text in capitals.")

    def test_command_that_fails_to_start_is_skipped(self):
        r = Registry(commands_config(
            broken={"permission": "public", "handler": "tests.test_registry:Broken"},
            shout={"permission": "public", "handler": "tests.test_registry:shout"}), available={})
        self.assertEqual(list(r.build(Directory(), None)), ["shout"])
        self.assertEqual(r.warnings, ["Could not start broken: no radio; skipped."])


class ExamplePluginTest(unittest.IsolatedAsyncioTestCase):
    """The example in examples/mesh-dice, loaded the way a config would name it."""

    def setUp(self):
        sys.path.insert(0, str(EXAMPLE_PLUGIN))
        self.addCleanup(sys.path.remove, str(EXAMPLE_PLUGIN))
        self.addCleanup(sys.modules.pop, "mesh_dice", None)
        config = commands_config(roll={"permission": "public", "handler": "mesh_dice:roll", "max_dice": 3},
                                 flip={"permission": "public", "handler": "mesh_dice:FlipCommand"})
        self.commands = Registry(config, available={}).build(Directory(), None)

    async def test_roll(self):
        roll = self.commands["roll"]
        self.assertEqual(roll.usage, "roll [NdS]")
        reply = await roll.execute("2d6", DANA)
        self.assertRegex(reply, r"^Dana rolled 2d6: \d+ \(\d \+ \d\)$")
        with self.assertRaisesRegex(Exception, "1-3 dice"):
            await roll.execute("4d6", DANA)  # max_dice from the config

    async def test_flip(self):
        result = await self.commands["flip"].execute("3", DANA)
        self.assertRegex(result.reply, r"^[HT]{3} \(\d heads\)$")

    def test_entry_points_declared(self):
        text = (EXAMPLE_PLUGIN / "pyproject.toml").read_text()
        self.assertIn(f'[project.entry-points."{ENTRY_POINT_GROUP}"]', text)
        self.assertIn('roll = "mesh_dice:roll"', text)


if __name__ == "__main__":
    unittest.main()
