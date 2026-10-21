import unittest

from mesh_contingency.names import is_profane, name_problem


class NameTest(unittest.TestCase):
    def test_radio_names_with_spaces_and_punctuation(self):
        for name in ["Ridge Base 1", "Sam's T-Deck", "Base #2 (north)", "José", "x" * 40, "\U0001f525 Fire"]:
            self.assertIsNone(name_problem(name), name)

    def test_unusable_radio_names(self):
        self.assertIn("has no name", name_problem(""))
        self.assertIn("has no name", name_problem("   "))
        for name in ["two\nlines", "bell\x07", "esc\x1b[2J", "c1\x9b"]:
            self.assertIn("control characters", name_problem(name), repr(name))
        for name in ["«Sam»", "Sam » x"]:
            self.assertIn("« or »", name_problem(name), name)
        self.assertIn("isn't allowed", name_problem("Big Ass"))

    def test_profanity(self):
        for name in ["Ass", "ASS", "BigAss", "assHat", "B1gAss", "5h1t", "BigShitHead", "fuckface", "n4z1",
                     "Big Ass", "big-ass radio"]:
            self.assertTrue(is_profane(name), name)

    def test_real_names_that_contain_a_word(self):
        for name in ["Bass", "Cassidy", "Hancock", "Dickson", "Fagan", "Sexton", "Titan", "Assistant", "Grapes",
                     "Ridge", "Gamma1", "Ridge Base 1", "Glass House"]:
            self.assertFalse(is_profane(name), name)


if __name__ == "__main__":
    unittest.main()
