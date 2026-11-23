import unittest

from mesh_contingency.api import ADMIN, PUBLIC, USER, Command, CommandError, Sender
from mesh_contingency.commands.help import HelpCommand
from mesh_contingency.testing import make_context

USER_KEY, ADMIN_KEY = "d0" * 32, "ad" * 32


class Echo(Command):
    args = "<text>"
    summary = "Say it back"

    async def execute(self, text, sender):
        return text


class HelpCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.commands = {}
        ctx = dict(users={USER_KEY: {}}, admins={ADMIN_KEY}, commands=self.commands)
        for name, cls, level in [("help", HelpCommand, PUBLIC), ("echo", Echo, PUBLIC),
                                 ("mine", Echo, USER), ("alert", Echo, ADMIN)]:
            cmd = cls(make_context(name, **ctx))
            cmd.permission = level
            self.commands[name] = cmd
        self.help = self.commands["help"]

    async def ask(self, text, key):
        return (await self.help.execute(text, Sender("x", key))).reply

    async def test_lists_what_the_sender_may_run(self):
        self.assertEqual(await self.ask("", "ff" * 32), "commands: help, echo. Send help <command> for usage")
        self.assertEqual(await self.ask("", USER_KEY), "commands: help, echo, mine. Send help <command> for usage")
        self.assertEqual(await self.ask("", ADMIN_KEY), "commands: help, echo, alert. Send help <command> for usage")

    async def test_usage_of_one_command(self):
        self.assertEqual(await self.ask("ECHO", "ff" * 32), "echo <text> - Say it back")
        self.assertEqual(await self.ask("help", "ff" * 32),
                         "help [command] - List the commands you can use, or show how to use one")

    async def test_without_summary(self):
        self.commands["echo"].summary = ""
        self.assertEqual(await self.ask("echo", "ff" * 32), "echo <text>")

    async def test_hidden_and_unknown_commands_look_the_same(self):
        for name in ("alert", "nope"):
            with self.subTest(name=name), self.assertRaisesRegex(CommandError, f"^help: no command {name}$"):
                await self.ask(name, USER_KEY)


if __name__ == "__main__":
    unittest.main()
