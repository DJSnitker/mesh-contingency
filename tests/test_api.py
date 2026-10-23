import threading
import unittest

from mesh_contingency.api import (
    ADMIN,
    CONSOLE,
    DEFAULT_TIMEOUT,
    DISABLED,
    LEVELS,
    MAX_PARTS,
    MAX_REPLY_LEN,
    PUBLIC,
    USER,
    Command,
    CommandResult,
    Context,
    FunctionCommand,
    Sender,
    command,
    is_authorized,
    split_reply,
    to_messages,
)
from mesh_contingency.directory import Directory
from mesh_contingency.testing import make_context

DANA = Sender("Dana", "d0" * 32)


class FitReplyTest(unittest.TestCase):
    def test_joins_sections_in_order(self):
        self.assertEqual(Command.fit_reply("12345", ["a", "b", "c"]), "12345 a | b | c")

    def test_no_sections(self):
        self.assertEqual(Command.fit_reply("12345", []), "12345")

    def test_drops_sections_that_do_not_fit(self):
        # "P a" (3) + " | " + 10 chars = 16 > 15, so the second section is
        # dropped, but the shorter third one still fits.
        self.assertEqual(Command.fit_reply("P", ["a", "x" * 10, "c"], limit=15), "P a | c")

    def test_truncates_first_section_instead_of_dropping_it(self):
        text = Command.fit_reply("P", ["x" * 50, "b"], limit=20)
        self.assertEqual(len(text), 20)
        self.assertTrue(text.startswith("P xxx"))
        self.assertTrue(text.endswith("..."))

    def test_exact_fit_is_kept(self):
        text = Command.fit_reply("P", ["x" * (MAX_REPLY_LEN - 2)])
        self.assertEqual(len(text), MAX_REPLY_LEN)
        self.assertFalse(text.endswith("..."))

    def test_default_limit_is_mesh_limit(self):
        self.assertEqual(MAX_REPLY_LEN, 133)
        text = Command.fit_reply("P", ["x" * 500])
        self.assertEqual(len(text), MAX_REPLY_LEN)


class SplitReplyTest(unittest.TestCase):
    def test_fitting_text_is_one_unnumbered_message(self):
        self.assertEqual(Command.split_reply("short"), ["short"])
        text = "x" * MAX_REPLY_LEN
        self.assertEqual(Command.split_reply(text), [text])

    def test_numbered_parts_rejoin_to_the_text(self):
        text = " ".join(f"word{i}" for i in range(60))  # ~410 chars
        parts = Command.split_reply(text)
        self.assertEqual(len(parts), 4)
        for i, part in enumerate(parts, 1):
            self.assertLessEqual(len(part), MAX_REPLY_LEN)
            self.assertTrue(part.startswith(f"({i}/4) "))
        self.assertEqual(" ".join(p.split(" ", 1)[1] for p in parts), text)

    def test_breaks_between_words(self):
        self.assertEqual(Command.split_reply("aaaa bbbb cccc-dddd", limit=16),
                         ["(1/2) aaaa bbbb", "(2/2) cccc-dddd"])

    def test_numbering_width_grows_past_nine_parts(self):
        text = " ".join(["abcdefghi"] * 120)
        parts = Command.split_reply(text)
        self.assertGreaterEqual(len(parts), 10)
        self.assertTrue(parts[0].startswith(f"(1/{len(parts)}) "))
        self.assertTrue(all(len(p) <= MAX_REPLY_LEN for p in parts))
        self.assertEqual(" ".join(p.split(" ", 1)[1] for p in parts), text)

    def test_overlong_word_is_cut(self):
        parts = Command.split_reply("y" * 30, limit=20)
        self.assertTrue(all(len(p) <= 20 for p in parts))
        self.assertEqual("".join(p.split(" ", 1)[1] for p in parts), "y" * 30)


class BaseTypesTest(unittest.TestCase):
    def test_command_defaults(self):
        self.assertEqual(Command.permission, DISABLED)  # until the config grants one
        self.assertEqual(Command.timeout, DEFAULT_TIMEOUT)
        self.assertTrue(Command.enabled)
        self.assertEqual(LEVELS, (PUBLIC, USER, ADMIN, DISABLED))

    def test_command_is_abstract(self):
        with self.assertRaises(TypeError):
            Command(make_context("x"))

    def test_name_and_usage_come_from_context(self):
        class Tide(Command):
            args = "<station>"

            async def execute(self, text, sender):
                pass  # pragma: no cover

        cmd = Tide(make_context("tide"))
        self.assertEqual((cmd.name, cmd.usage), ("tide", "tide <station>"))
        self.assertEqual(Tide(make_context("tides")).usage, "tides <station>")
        Tide.args = ""
        self.assertEqual(cmd.usage, "tide")

    def test_reply_helpers_on_command(self):
        self.assertIs(Command.split_reply, split_reply)

    def test_dataclasses(self):
        self.assertEqual(CommandResult("c", "r"), CommandResult(console="c", reply="r"))
        self.assertEqual(Sender("Dana", "d0" * 32).public_key, "d0" * 32)


class IsAuthorizedTest(unittest.TestCase):
    def check(self, permission, key):
        cmd = type("C", (), {"permission": permission})()
        users, admins = {"d0" * 32: {}}, {"ad" * 32}
        ctx = Context(name="x", directory=Directory(users, admins))
        result = is_authorized(cmd, Sender("x", key), users, admins)
        self.assertEqual(ctx.allowed(cmd, Sender("x", key)), result)
        return result

    def test_matrix(self):
        self.assertTrue(self.check(PUBLIC, "ff" * 32))
        self.assertTrue(self.check(USER, "d0" * 32))
        self.assertFalse(self.check(USER, "ad" * 32))
        self.assertTrue(self.check(ADMIN, "ad" * 32))
        self.assertFalse(self.check(ADMIN, "d0" * 32))
        self.assertFalse(self.check(DISABLED, "ad" * 32))
        self.assertFalse(self.check("other", "ad" * 32))

    def test_the_web_console_is_an_admin_but_not_a_user(self):
        self.assertTrue(self.check(ADMIN, CONSOLE.public_key))
        self.assertTrue(self.check(PUBLIC, CONSOLE.public_key))
        self.assertFalse(self.check(USER, CONSOLE.public_key))
        self.assertFalse(self.check(DISABLED, CONSOLE.public_key))


class ToMessagesTest(unittest.TestCase):
    def test_none_and_short_text(self):
        self.assertEqual(to_messages(None), [])
        self.assertEqual(to_messages("hi"), ["hi"])
        self.assertEqual(to_messages(""), [""])

    def test_long_text_split(self):
        text = " ".join(["word"] * 60)
        self.assertEqual(to_messages(text), split_reply(text))

    def test_text_too_long_for_max_parts_is_shortened(self):
        messages = to_messages(" ".join(["word"] * 1000))
        self.assertEqual(len(messages), MAX_PARTS)
        self.assertTrue(messages[0].startswith(f"(1/{MAX_PARTS}) word"))
        self.assertTrue(messages[-1].endswith("..."))
        self.assertTrue(all(len(m) <= MAX_REPLY_LEN for m in messages))

    def test_list_sent_as_given_within_limits(self):
        self.assertEqual(to_messages(["a", "b"]), ["a", "b"])
        messages = to_messages(["x" * 200] + ["m"] * 20)
        self.assertEqual(len(messages), MAX_PARTS)
        self.assertEqual(messages[0], "x" * (MAX_REPLY_LEN - 3) + "...")


class FunctionCommandTest(unittest.IsolatedAsyncioTestCase):
    async def test_async_function(self):
        async def hello(text, sender, ctx):
            """Say hello.

            More detail that help doesn't show."""
            return f"{ctx.options['greeting']} {sender.name}: {text}"

        cmd = FunctionCommand(make_context("hello", options={"greeting": "hi"}), hello)
        self.assertEqual(await cmd.execute("there", DANA), "hi Dana: there")
        self.assertEqual((cmd.name, cmd.usage, cmd.summary), ("hello", "hello", "Say hello."))

    async def test_sync_function_runs_off_the_event_loop(self):
        loop_thread = threading.get_ident()

        @command(args="<n>", summary="Double it")
        def double(text, sender, ctx):
            return (str(int(text) * 2), threading.get_ident())

        cmd = FunctionCommand(make_context("double"), double)
        reply, thread = await cmd.execute("21", DANA)
        self.assertEqual(reply, "42")
        self.assertNotEqual(thread, loop_thread)
        self.assertEqual((cmd.usage, cmd.summary), ("double <n>", "Double it"))

    async def test_no_docstring(self):
        cmd = FunctionCommand(make_context("x"), lambda text, sender, ctx: None)
        self.assertEqual((cmd.args, cmd.summary), ("", ""))
        self.assertIsNone(await cmd.execute("", DANA))

    def test_command_decorator_returns_the_function(self):
        def f(text, sender, ctx):
            pass  # pragma: no cover
        self.assertIs(command(args="a", summary="s")(f), f)
        self.assertEqual((f.args, f.summary), ("a", "s"))


if __name__ == "__main__":
    unittest.main()
