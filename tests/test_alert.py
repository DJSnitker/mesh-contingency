import unittest

from mesh_commands import MAX_PARTS, MAX_REPLY_LEN, CommandError, Sender
from mesh_commands.testing import FakeMeshCore, event, make_context
from meshcore import EventType

from mesh_contingency.alerts import PUBLIC_SECRET, format_alerts, short_time
from mesh_contingency.commands.alert import AlertCommand
from mesh_contingency.state import State

ADMIN = Sender("Admin", "ad" * 32)
FLOOD = {"event": "Flood Warning", "ends": "2026-10-20T18:00:00-05:00", "areaDesc": "Miami-Dade"}
WIND = {"event": "Wind Advisory", "ends": None, "expires": "2026-10-21T09:30:00-05:00"}


class FormatTest(unittest.TestCase):
    def test_short_time(self):
        self.assertEqual(short_time("2026-10-20T18:00:00-05:00"), "Tue 6:00PM")
        self.assertEqual(short_time("2026-10-21T00:05:00-05:00"), "Wed 12:05AM")
        self.assertEqual(short_time("soon"), "soon")
        self.assertIsNone(short_time(None))

    def test_one_message_per_alert(self):
        self.assertEqual(format_alerts("33101", [FLOOD, WIND, dict(FLOOD, areaDesc="Broward")]), [
            "33101 ALERT: Flood Warning | until Tue 6:00PM | Miami-Dade",
            "33101 ALERT: Wind Advisory | until Wed 9:30AM",
        ])

    def test_limits(self):
        alerts = [{"event": f"Hazard {i} " + "x" * 200, "ends": str(i)} for i in range(20)]
        messages = format_alerts("33101", alerts, limit=100)
        self.assertEqual(len(messages), MAX_PARTS)
        self.assertTrue(all(len(m) <= 100 for m in messages))
        self.assertEqual(messages[-1], "33101: 13 more alerts; see weather.gov")


class AlertCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.radio = FakeMeshCore()
        self.state = State()
        self.cmd = AlertCommand(make_context("alert", radio=self.radio, extras={"state": self.state}))

    async def test_posts_the_message_to_public(self):
        result = await self.cmd.execute("  Shelter open at the  church on 5th  ", ADMIN)
        self.assertEqual(self.radio.channel_sent, [(0, "Shelter open at the  church on 5th")])
        self.assertEqual(result.reply, "alert: posted to Public")
        self.assertEqual(result.console, "Posted to Public (slot 0): Shelter open at the  church on 5th")

    async def test_public_in_another_slot(self):
        self.radio.channels[0] = ("#local", bytes(range(16)))
        self.radio.channels[3] = ("Öffentlich", PUBLIC_SECRET)  # found by its key, whatever it's called
        await self.cmd.execute("hello", ADMIN)
        self.assertEqual(self.radio.channel_sent, [(3, "hello")])

    async def test_a_channel_named_public_with_another_key_is_not_used(self):
        self.radio.channels[0] = ("Public", bytes(range(16)))
        with self.assertRaisesRegex(CommandError, "^alert: no Public channel on the radio; add MeshCore's Public "
                                                  "channel back in its app; nothing posted$"):
            await self.cmd.execute("hello", ADMIN)
        self.assertEqual(self.radio.channel_sent, [])
        self.assertEqual(self.radio.channels[1], ("", bytes(16)))  # nothing added

    async def test_an_old_channel_option_is_ignored(self):
        cmd = AlertCommand(make_context("alert", options={"channel": "#storm"}, radio=self.radio))
        await cmd.execute("hello", ADMIN)
        self.assertEqual(self.radio.channel_sent, [(0, "hello")])
        self.assertNotIn("#storm", [name for name, _ in self.radio.channels])

    async def test_a_message_must_fit_with_the_node_name(self):
        self.radio.self_info["name"] = "N" * 30
        limit = MAX_REPLY_LEN - 32
        await self.cmd.execute("x" * limit, ADMIN)
        with self.assertRaisesRegex(CommandError, rf"^alert: too long for one channel message \({limit + 1} "
                                                  rf"characters; at most {limit}\); nothing posted$"):
            await self.cmd.execute("x" * (limit + 1), ADMIN)
        self.assertEqual(len(self.radio.channel_sent), 1)

    async def test_usage(self):
        for text in ("", "   "):
            with self.subTest(text=text), self.assertRaisesRegex(CommandError, r"^usage: alert <message>$"):
                await self.cmd.execute(text, ADMIN)
        self.assertEqual(self.radio.channel_sent, [])

    async def test_radio_rejects_message(self):
        self.radio.channel_result = event(EventType.ERROR, {"reason": "busy"})
        with self.assertRaisesRegex(RuntimeError, "rejected channel message 1 of 1"):
            await self.cmd.execute("hello", ADMIN)


if __name__ == "__main__":
    unittest.main()
