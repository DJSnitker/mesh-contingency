import unittest

from commands.base import ADMIN, MAX_REPLY_LEN, PUBLIC, USER, Command, CommandResult, Sender


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
        self.assertEqual(Command.permission, PUBLIC)
        self.assertTrue(Command.enabled)
        self.assertEqual(len({PUBLIC, USER, ADMIN}), 3)

    def test_command_is_abstract(self):
        with self.assertRaises(TypeError):
            Command()

    def test_dataclasses(self):
        self.assertEqual(CommandResult("c", "r"), CommandResult(console="c", reply="r"))
        self.assertEqual(Sender("Dana", "d0d0d0d0d0d0").key, "d0d0d0d0d0d0")


if __name__ == "__main__":
    unittest.main()
