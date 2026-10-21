import unittest

from mesh_contingency.sealing import SealError, check_passphrase, new_inbox_key, open_sealed, seal, unlock

PASSPHRASE = "blue-canoe-42x"


class SealingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inbox_key = new_inbox_key(PASSPHRASE)

    def test_inbox_key_keeps_no_secret(self):
        self.assertEqual(set(self.inbox_key), {"public", "salt", "n"})
        self.assertEqual(len(self.inbox_key["public"]), 64)
        self.assertNotIn(PASSPHRASE, repr(self.inbox_key))

    def test_seal_and_open(self):
        sealed = seal("meet at the shelter at 6", self.inbox_key)
        self.assertEqual(set(sealed), {"epk", "nonce", "ct"})
        self.assertNotIn("shelter", repr(sealed))
        self.assertEqual(open_sealed(sealed, unlock(PASSPHRASE, self.inbox_key)), "meet at the shelter at 6")

    def test_each_seal_is_different(self):
        self.assertNotEqual(seal("same", self.inbox_key), seal("same", self.inbox_key))

    def test_wrong_passphrase_unlocks_nothing(self):
        self.assertIsNone(unlock("blue-canoe-42y", self.inbox_key))

    def test_same_passphrase_gives_different_keys(self):
        other = new_inbox_key(PASSPHRASE)
        self.assertNotEqual(other["public"], self.inbox_key["public"])
        with self.assertRaises(SealError):
            open_sealed(seal("hi", self.inbox_key), unlock(PASSPHRASE, other))

    def test_changed_message_is_refused(self):
        sealed = seal("hello", self.inbox_key)
        sealed["ct"] = ("A" if sealed["ct"][0] != "A" else "B") + sealed["ct"][1:]
        with self.assertRaises(SealError):
            open_sealed(sealed, unlock(PASSPHRASE, self.inbox_key))
        with self.assertRaises(SealError):
            open_sealed({"epk": "?"}, unlock(PASSPHRASE, self.inbox_key))

    def test_broken_inbox_key(self):
        for broken in ({}, {"public": "zz", "salt": "00", "n": 1024}, {"public": "00" * 32}):
            with self.subTest(broken=broken), self.assertRaises(SealError):
                seal("hi", broken) if "salt" not in broken else unlock(PASSPHRASE, broken)

    def test_check_passphrase(self):
        for ok in ("a" * 12, "a" * 16, "blue-canoe-42x", "ünïcødé-pass!"):
            self.assertIsNone(check_passphrase(ok), ok)
        self.assertEqual(check_passphrase("a" * 11), "must be 12 to 16 characters")
        self.assertEqual(check_passphrase("a" * 17), "must be 12 to 16 characters")
        self.assertEqual(check_passphrase("blue canoe 42"), "can't contain spaces")
        self.assertEqual(check_passphrase("blue-canoe\x1b42"), "can't contain control characters")


if __name__ == "__main__":
    unittest.main()
