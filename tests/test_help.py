import unittest

from mesh_contingency.api import ADMIN, PUBLIC, USER, CommandError, Sender
from mesh_contingency.commands.help import HelpCommand
from mesh_contingency.commands.wx import WxCommand
from mesh_contingency.testing import make_context

USER_KEY, ADMIN_KEY = "d0" * 32, "ad" * 32


class HelpCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.commands = {}
        ctx = dict(users={USER_KEY: {}}, admins={ADMIN_KEY}, commands=self.commands)
        for name, cls, level in [("help", HelpCommand, PUBLIC), ("wx", WxCommand, PUBLIC),
                                 ("weather", WxCommand, USER), ("advert", WxCommand, ADMIN)]:
            cmd = cls(make_context(name, **ctx))
            cmd.permission = level
            self.commands[name] = cmd
        self.help = self.commands["help"]

    async def ask(self, text, key):
        return (await self.help.execute(text, Sender("x", key))).reply

    async def test_lists_what_the_sender_may_run(self):
        self.assertEqual(await self.ask("", "ff" * 32), "commands: help, wx. Send help <command> for usage")
        self.assertEqual(await self.ask("", USER_KEY), "commands: help, wx, weather. Send help <command> for usage")
        self.assertEqual(await self.ask("", ADMIN_KEY), "commands: help, wx, advert. Send help <command> for usage")

    async def test_usage_of_one_command(self):
        self.assertEqual(await self.ask("WX", "ff" * 32),
                         "wx <zipcode | county, ST> - Weather, precipitation and alerts for a US zipcode or county")
        self.assertEqual(await self.ask("help", "ff" * 32),
                         "help [command] - List the commands you can use, or show how to use one")

    async def test_without_summary(self):
        self.commands["wx"].summary = ""
        self.assertEqual(await self.ask("wx", "ff" * 32), "wx <zipcode | county, ST>")

    async def test_hidden_and_unknown_commands_look_the_same(self):
        for name in ("advert", "nope"):
            with self.subTest(name=name), self.assertRaisesRegex(CommandError, f"^help: no command {name}$"):
                await self.ask(name, USER_KEY)


if __name__ == "__main__":
    unittest.main()
