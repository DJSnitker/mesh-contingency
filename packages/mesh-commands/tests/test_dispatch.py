import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest import mock

from mesh_commands import ADMIN, DISABLED, PUBLIC, USER, Command, CommandError, Dispatcher, KeyRoles, Sender
from mesh_commands.dispatch import UNRECOGNIZED_COOLDOWN, UNRECOGNIZED_REPLY, nearest_command, parse_command
from mesh_commands.permissions import is_authorized
from mesh_commands.testing import make_context

ADMIN_KEY, USER_KEY, OTHER_KEY = "ad" * 32, "d0" * 32, "ff" * 32


class Echo(Command):
    args = "<text>"

    async def execute(self, text, sender):
        if text == "fail":
            raise CommandError("echo: no")
        return text or None


class ParseCommandTest(unittest.TestCase):
    COMMANDS = {"alert": "AL", "testalert": "TA"}

    def parse(self, text):
        return parse_command(text, self.COMMANDS)

    def test_name_and_text(self):
        self.assertEqual(self.parse("alert shelter open"), ("AL", "shelter open"))
        self.assertEqual(self.parse("  ALERT   shelter  "), ("AL", "shelter"))
        self.assertEqual(self.parse("testalert"), ("TA", ""))

    def test_text_keeps_inner_spacing(self):
        self.assertEqual(self.parse("alert a  two  spaces"), ("AL", "a  two  spaces"))
        self.assertEqual(self.parse("alert line1\nline2"), ("AL", "line1\nline2"))

    def test_not_a_command(self):
        for text in ("", "   ", "hello", "alerts now", "wx 10001"):
            self.assertIsNone(self.parse(text), text)


class NearestCommandTest(unittest.TestCase):
    NAMES = ["help", "alert", "testalert"]

    def test_close(self):
        for word, expected in [("hlep", "help"), ("ALRET", "alert"), ("testalret", "testalert"),
                               ("hello", None), ("test", None), ("x", None)]:
            self.assertEqual(nearest_command(word, self.NAMES), expected, word)

    def test_a_disabled_command_is_not_a_typo(self):
        self.assertIsNone(nearest_command("alerts", ["alert"], disabled=["alerts"]))

    def test_our_own_reply_is_not_a_command(self):
        # A node that echoes our replies back can't start a loop.
        self.assertIsNone(nearest_command("unknown", self.NAMES))
        self.assertIsNone(nearest_command(UNRECOGNIZED_REPLY.split()[0], self.NAMES))


class IsAuthorizedTest(unittest.TestCase):
    def test_matrix(self):
        roles = KeyRoles(users={USER_KEY}, admins={ADMIN_KEY})
        for level, key, expected in [(PUBLIC, OTHER_KEY, True), (PUBLIC, None, True), (USER, USER_KEY, True),
                                     (USER, ADMIN_KEY, False), (ADMIN, ADMIN_KEY, True), (ADMIN, USER_KEY, False),
                                     (ADMIN, None, False), (DISABLED, ADMIN_KEY, False), ("other", ADMIN_KEY, False)]:
            command = SimpleNamespace(permission=level)
            self.assertIs(is_authorized(command, Sender("x", key), roles), expected, (level, key))


class DispatcherTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = 1000.0
        self.enterContext(mock.patch("mesh_commands.dispatch.time.monotonic", lambda: self.clock))
        self.out = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.commands = {}
        for name, level, rate in [("echo", PUBLIC, None), ("alert", ADMIN, None), ("limited", PUBLIC, (1, 3600))]:
            cmd = Echo(make_context(name))
            cmd.permission, cmd.rate = level, rate
            self.commands[name] = cmd
        self.sent = []

        async def send(key, text):
            self.sent.append((key, text))

        self.dispatcher = Dispatcher(self.commands, KeyRoles(admins={ADMIN_KEY}), send, disabled=["off"])

    async def dm(self, key, text, prefix=None):
        prefix = prefix or (key or "c0ffeec0ffee")[:12]
        await self.dispatcher.handle(prefix, Sender("Name", key), text)

    async def test_runs_and_replies_to_the_full_key(self):
        await self.dm(OTHER_KEY, "echo hi there")
        self.assertEqual(self.sent, [(OTHER_KEY, "hi there")])
        out = self.out.getvalue()
        self.assertIn(f"[{OTHER_KEY[:12]} Name] echo\n  -> running echo\n  -> replied (8 chars)\n", out)
        self.assertNotIn("hi there", out)

    async def test_an_unidentified_sender_is_answered_by_prefix(self):
        await self.dm(None, "echo hi", prefix="c0ffeec0ffee")
        self.assertEqual(self.sent, [("c0ffeec0ffee", "hi")])

    async def test_no_reply(self):
        await self.dm(OTHER_KEY, "echo")
        self.assertEqual(self.sent, [])
        self.assertIn("-> no reply", self.out.getvalue())

    async def test_a_refusal_is_sent_back(self):
        await self.dm(OTHER_KEY, "echo fail")
        self.assertEqual(self.sent, [(OTHER_KEY, "echo: no")])

    async def test_denied_looks_like_unknown(self):
        await self.dm(OTHER_KEY, "alert hi")
        self.assertEqual(self.sent, [(OTHER_KEY, UNRECOGNIZED_REPLY)])
        self.assertIn("alert denied: sender not approved", self.out.getvalue())
        await self.dm(ADMIN_KEY, "alert hi")
        self.assertEqual(self.sent[-1], (ADMIN_KEY, "hi"))

    async def test_unrecognized_cooldown_per_sender(self):
        await self.dm(OTHER_KEY, "hello")
        await self.dm(OTHER_KEY, "alert x")  # a denial shares the cooldown
        await self.dm(USER_KEY, "hello")
        self.assertEqual(self.sent, [(OTHER_KEY, UNRECOGNIZED_REPLY), (USER_KEY, UNRECOGNIZED_REPLY)])
        self.assertIn(f"not replying (replied within {UNRECOGNIZED_COOLDOWN}s)", self.out.getvalue())
        self.clock += UNRECOGNIZED_COOLDOWN
        await self.dm(OTHER_KEY, "hello")
        self.assertEqual(self.sent[-1], (OTHER_KEY, UNRECOGNIZED_REPLY))

    async def test_blank_gets_nothing(self):
        await self.dm(OTHER_KEY, "  ")
        self.assertEqual(self.sent, [])

    async def test_suggestions_only_for_senders_with_rights(self):
        await self.dm(OTHER_KEY, "ecoh hi")  # only public commands: told nothing
        await self.dm(ADMIN_KEY, "alret shelter open")
        await self.dm(ADMIN_KEY, "alret again")  # no cooldown on suggestions
        await self.dm(ADMIN_KEY, "off")  # a disabled command isn't a typo
        self.assertEqual(self.sent, [
            (OTHER_KEY, UNRECOGNIZED_REPLY),
            (ADMIN_KEY, "unknown command alret; did you mean alert? help lists yours"),
            (ADMIN_KEY, "unknown command alret; did you mean alert? help lists yours"),
            (ADMIN_KEY, UNRECOGNIZED_REPLY)])

    async def test_rate_limit_told_once_then_silent(self):
        for _ in range(3):
            await self.dm(OTHER_KEY, "limited hi")
        self.assertEqual(self.sent, [(OTHER_KEY, "hi"), (OTHER_KEY, "limited: limit reached, try again in 60 min")])
        out = self.out.getvalue()
        self.assertIn("  -> limited limit reached (1/hour); replying once\n", out)
        self.assertIn("  -> limited limit reached; not replying\n", out)


if __name__ == "__main__":
    unittest.main()
