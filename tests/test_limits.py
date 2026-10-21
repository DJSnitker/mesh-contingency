import unittest
from unittest import mock

from mesh_contingency.limits import EmailLog, Limits, RateLimiter, describe_rate, parse_rate, wait_text
from mesh_contingency.registry import Registry


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
        self.assertEqual((limits.emails_per_day, limits.emails_per_day_total), (50, 200))

    def test_settings(self):
        limits = Limits.from_config({"limits": {"public_rate": "3/minute", "admin_rate": "100/day",
                                                "emails_per_day": 0}})
        self.assertEqual(limits.rates["public"], (3, 60))
        self.assertEqual(limits.rates["admin"], (100, 86400))
        self.assertEqual(limits.emails_per_day, 0)

    def test_mistakes(self):
        with self.assertRaisesRegex(SystemExit, r"\[limits\] may only set"):
            Limits.from_config({"limits": {"guest_rate": "1/hour"}})
        with self.assertRaisesRegex(SystemExit, r"\[limits\] emails_per_day must be"):
            Limits.from_config({"limits": {"emails_per_day": -1}})
        with self.assertRaisesRegex(SystemExit, r"\[limits\] user_rate rate must look"):
            Limits.from_config({"limits": {"user_rate": "lots"}})

    def test_registry_applies_rates(self):
        registry = Registry({"limits": {"user_rate": "2/minute"}, "commands": {
            "help": {"permission": "public"}, "roster": {"permission": "user"},
            "wx": {"permission": "public", "rate": "1/day"}, "advert": {"permission": "admin"},
            "verse": {"permission": "public", "rate": "none"}}})
        self.assertEqual({name: spec.rate for name, spec in registry.specs.items()},
                         {"help": (10, 3600), "roster": (2, 60), "wx": (1, 86400), "advert": None, "verse": None})
        self.assertNotIn("rate", registry.specs["wx"].options)
        with self.assertRaisesRegex(SystemExit, r"\[commands.wx\] rate must look"):
            Registry({"commands": {"wx": {"permission": "public", "rate": "often"}}})


class RateLimiterTest(unittest.TestCase):
    def setUp(self):
        self.clock = 1_000.0
        self.enterContext(mock.patch("mesh_contingency.limits.time.monotonic", lambda: self.clock))

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


class EmailLogTest(unittest.TestCase):
    def test_counts_the_last_day(self):
        now = [1_000_000.0]
        with mock.patch("mesh_contingency.limits.time.time", lambda: now[0]):
            log = EmailLog()
            log.record("dana", 2)
            now[0] += 3600
            log.record("bob", 1)
            log.record("dana", 1)
            self.assertEqual((log.sends("dana"), log.sends("bob"), log.addresses()), (2, 1, 4))
            now[0] += 86400 - 3600 + 1
            self.assertEqual((log.sends("dana"), log.sends("bob"), log.addresses()), (1, 1, 2))


class WaitTextTest(unittest.TestCase):
    def test_wait_text(self):
        self.assertEqual(wait_text(1), "1 min")
        self.assertEqual(wait_text(61), "2 min")
        self.assertEqual(wait_text(23 * 60), "23 min")
        self.assertEqual(wait_text(5 * 3600 - 30), "5 h")


if __name__ == "__main__":
    unittest.main()
