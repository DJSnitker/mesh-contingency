import unittest
from unittest import mock

from mesh_commands.limits import Limits, RateLimiter, describe_rate, parse_rate, wait_text
from mesh_commands.registry import Registry


class ParseRateTest(unittest.TestCase):
    def test_rates(self):
        self.assertEqual(parse_rate("5/hour", ""), (5, 3600))
        self.assertEqual(parse_rate(" 1 / minute ", ""), (1, 60))
        self.assertEqual(parse_rate("100/day", ""), (100, 86400))
        self.assertIsNone(parse_rate("none", ""))

    def test_mistakes(self):
        for value in ("5", "5/week", "0/hour", "-1/hour", 5, None, "five/hour"):
            with self.subTest(value=value), self.assertRaisesRegex(SystemExit, r'^\[commands.wx\] rate must look'):
                parse_rate(value, "[commands.wx]")

    def test_describe(self):
        self.assertEqual(describe_rate((5, 3600)), "5/hour")
        self.assertEqual(describe_rate(None), "none")


class LimitsConfigTest(unittest.TestCase):
    def test_defaults(self):
        limits = Limits.from_config({})
        self.assertEqual(limits.rates, {"public": (10, 3600), "user": (30, 3600), "admin": None})

    def test_settings(self):
        limits = Limits.from_config({"limits": {"public_rate": "3/minute", "admin_rate": "100/day"}})
        self.assertEqual(limits.rates["public"], (3, 60))
        self.assertEqual(limits.rates["admin"], (100, 86400))

    def test_old_email_caps_are_ignored(self):
        limits = Limits.from_config({"limits": {"emails_per_day": 50}}, ignore={"emails_per_day"})
        self.assertEqual(limits, Limits())
        with self.assertRaisesRegex(SystemExit, r"\[limits\] may only set"):
            Limits.from_config({"limits": {"emails_per_day": 50}})

    def test_mistakes(self):
        with self.assertRaisesRegex(SystemExit, r"\[limits\] may only set"):
            Limits.from_config({"limits": {"guest_rate": "1/hour"}})
        with self.assertRaisesRegex(SystemExit, r"\[limits\] user_rate rate must look"):
            Limits.from_config({"limits": {"user_rate": "lots"}})

    def test_registry_applies_rates(self):
        help_handler = "mesh_commands.builtin.help:HelpCommand"
        available = {name: help_handler for name in ("help", "mine", "alert", "testalert", "other")}
        registry = Registry({"limits": {"user_rate": "2/minute"}, "commands": {
            "help": {"permission": "public"}, "mine": {"permission": "user"},
            "alert": {"permission": "admin", "rate": "1/day"}, "testalert": {"permission": "admin"},
            "other": {"permission": "public", "rate": "none"}}}, available=available)
        self.assertEqual({name: spec.rate for name, spec in registry.specs.items()},
                         {"help": (10, 3600), "mine": (2, 60), "alert": (1, 86400), "testalert": None,
                          "other": None})
        self.assertNotIn("rate", registry.specs["alert"].options)
        with self.assertRaisesRegex(SystemExit, r"\[commands.alert\] rate must look"):
            Registry({"commands": {"alert": {"permission": "admin", "rate": "often"}}}, available=available)


class RateLimiterTest(unittest.TestCase):
    def setUp(self):
        self.clock = 1_000.0
        self.enterContext(mock.patch("mesh_commands.limits.time.monotonic", lambda: self.clock))

    def test_sliding_window_and_one_notice(self):
        limiter = RateLimiter()
        self.assertEqual(limiter.check("dana", "wx", (2, 3600)), (0, False))
        self.clock += 600
        self.assertEqual(limiter.check("dana", "wx", (2, 3600)), (0, False))
        self.assertEqual(limiter.check("dana", "wx", (2, 3600)), (3000, True))  # told once
        self.assertEqual(limiter.check("dana", "wx", (2, 3600)), (3000, False))  # then silence
        self.clock += 3000
        self.assertEqual(limiter.check("dana", "wx", (2, 3600)), (0, False))  # the first use expired
        self.assertEqual(limiter.check("dana", "wx", (2, 3600))[1], True)  # told again next time

    def test_per_sender_and_command(self):
        limiter = RateLimiter()
        limiter.check("dana", "wx", (1, 60))
        self.assertEqual(limiter.check("bob", "wx", (1, 60)), (0, False))
        self.assertEqual(limiter.check("dana", "verse", (1, 60)), (0, False))
        self.assertEqual(limiter.check("dana", "wx", None), (0, False))


class WaitTextTest(unittest.TestCase):
    def test_wait_text(self):
        self.assertEqual(wait_text(1), "1 min")
        self.assertEqual(wait_text(61), "2 min")
        self.assertEqual(wait_text(23 * 60), "23 min")
        self.assertEqual(wait_text(5 * 3600 - 30), "5 h")


if __name__ == "__main__":
    unittest.main()
