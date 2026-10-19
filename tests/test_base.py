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
