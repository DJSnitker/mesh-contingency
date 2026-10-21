import unittest

from mesh_contingency.api import CommandError
from mesh_contingency.names import check_name, is_profane, name_problem, suggest


class NameTest(unittest.TestCase):
    def test_letters_and_numbers(self):
        for name in ["SamJones", "Sparky", "KE5OWL", "x" * 32, "7"]:
            self.assertIsNone(name_problem(name), name)
        for name in ["", "Sam Jones", "Sam-Jones", "Sam_Jones", "José", "Sam\n", "x" * 33, 'a"b']:
            self.assertIn("letters and numbers", name_problem(name), repr(name))

    def test_profanity(self):
        for name in ["Ass", "ASS", "BigAss", "assHat", "B1gAss", "5h1t", "BigShitHead", "fuckface", "n4z1"]:
            self.assertTrue(is_profane(name), name)

    def test_real_names_that_contain_a_word(self):
        for name in ["Bass", "Cassidy", "Hancock", "Dickson", "Fagan", "Sexton", "Titan", "Assistant", "Grapes",
                     "KE5OWL", "Ammo1"]:
            self.assertFalse(is_profane(name), name)

    def test_check_name(self):
        check_name("join", "Sparky")
        with self.assertRaisesRegex(CommandError, "^join: that name isn't allowed; choose another$"):
            check_name("join", "BigAss")

    def test_suggest(self):
        self.assertEqual(suggest("KE5OWL R1"), "KE5OWLR1")
        self.assertEqual(suggest("Bob T-1000"), "BobT1000")
        self.assertIsNone(suggest("Big-Ass"))
        self.assertIsNone(suggest("\U0001f525"))
        self.assertEqual(suggest("x" * 40), "x" * 32)


if __name__ == "__main__":
    unittest.main()
