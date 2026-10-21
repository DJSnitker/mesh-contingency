import unittest

from meshcore import EventType

from mesh_contingency.alerts import format_alerts, hashtag_secret, short_time
from mesh_contingency.api import MAX_PARTS, MAX_REPLY_LEN, CommandError, Sender
from mesh_contingency.commands.alert import AlertCommand
from mesh_contingency.state import HISTORY_FILE, State
from mesh_contingency.testing import FakeMeshCore, event, make_context

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
        self.assertEqual(messages[-1], "33101: 13 more alerts; check wx or weather.gov")


class AlertCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.radio = FakeMeshCore()
        self.state = State()
        self.cmd = AlertCommand(make_context("alert", radio=self.radio, state=self.state))

    async def test_posts_the_message_to_the_channel(self):
        result = await self.cmd.execute("  Shelter open at the  church on 5th  ", ADMIN)
        self.assertEqual(self.radio.channels[1], ("#contingency-wx", hashtag_secret("#contingency-wx")))
        self.assertEqual(self.radio.channel_sent, [(1, "Shelter open at the  church on 5th")])
        self.assertEqual(result.reply, "alert: posted to #contingency-wx")
        self.assertEqual(result.console,
                         "Posted to #contingency-wx (slot 1, added to the radio): Shelter open at the  church on 5th")
        entries = self.state.store(HISTORY_FILE).data["entries"]
        self.assertEqual([(e["by"], e["what"]) for e in entries],
                         [("Admin", "posted to #contingency-wx: Shelter open at the  church on 5th")])

    async def test_start_adds_the_channel_once(self):
        self.assertEqual(await self.cmd.start(), "alert: #contingency-wx is channel slot 1 (added to the radio).")
        self.assertEqual(await self.cmd.start(), "alert: #contingency-wx is channel slot 1.")
        self.assertEqual([c[0] for c in self.radio.channels].count("#contingency-wx"), 1)

    async def test_uses_the_channel_already_on_the_radio(self):
        self.radio.channels[5] = ("#Contingency-WX", hashtag_secret("#contingency-wx"))
        result = await self.cmd.execute("hello", ADMIN)
        self.assertEqual(self.radio.channel_sent, [(5, "hello")])
        self.assertNotIn("added", result.console)
        self.assertEqual(self.radio.channels[1], ("", bytes(16)))  # nothing added

    async def test_same_name_with_another_key_is_not_used(self):
        self.radio.channels[1] = ("#contingency-wx", bytes(range(16)))  # a private channel by that name
        await self.cmd.execute("hello", ADMIN)
        self.assertEqual(self.radio.channel_sent[0][0], 2)

    async def test_no_free_slot(self):
        self.radio.channels[1:] = [(f"ch{i}", bytes([i]) * 16) for i in range(1, 8)]
        with self.assertRaisesRegex(CommandError, "^alert: no free channel slot on the radio for #contingency-wx$"):
            await self.cmd.execute("hello", ADMIN)
        self.assertEqual(self.radio.channel_sent, [])

    async def test_channel_from_config(self):
        cmd = AlertCommand(make_context("alert", options={"channel": "#storm"}, radio=self.radio, state=self.state))
        await cmd.execute("hello", ADMIN)
        self.assertEqual(self.radio.channels[1][0], "#storm")
        for bad in ("storm", "#", "#" + "x" * 31, 5):
            with self.subTest(channel=bad), self.assertRaisesRegex(ValueError, "hashtag channel"):
                AlertCommand(make_context("alert", options={"channel": bad}, radio=self.radio))

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
