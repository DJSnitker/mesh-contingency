"""radio: the radio's settings, shown to admins and changed from the web console."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from meshcore import EventType

from mesh_contingency.api import CONSOLE, CommandError, Sender
from mesh_contingency.commands.radio import RadioCommand, matching_presets, parse_freq
from mesh_contingency.radio_presets import PRESETS
from mesh_contingency.state import HISTORY_FILE, State
from mesh_contingency.testing import FakeMeshCore, event, make_context

ADMIN = Sender("Net Control", "ad" * 32)


class PresetTest(unittest.TestCase):
    def test_parse_a_preset_or_the_four_values(self):
        self.assertEqual(parse_freq("usa"), (910.525, 62.5, 7, 5))
        self.assertEqual(parse_freq("EU/UK (Narrow)"), (869.618, 62.5, 8, 8))
        self.assertEqual(parse_freq("915.8 250 10 5"), (915.8, 250, 10, 5))
        self.assertEqual(parse_freq("433.65 62.5 8 8"), (433.65, 62.5, 8, 8))

    def test_refuses_what_isnt_a_setting(self):
        for text, why in [("mars", "give a preset"), ("915 250 10", "give a preset"),
                          ("x 250 10 5", "numbers"), ("1200 250 10 5", "isn't a LoRa frequency"),
                          ("915 200 10 5", "bandwidth 200 kHz isn't one of"), ("915 250 13 5", "SF is 5 to 12"),
                          ("915 250 10 9", "CR is 5 to 8")]:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, why):
                parse_freq(text)

    def test_matching(self):
        self.assertEqual(matching_presets(910.525, 62.5, 7, 5), ["Canada", "USA"])
        self.assertEqual(matching_presets(910.525, 62.5, 7, 8), [])

    def test_the_presets_are_whole(self):
        self.assertEqual(len(PRESETS), 26)
        for title, freq, bw, sf, cr, _ in PRESETS:
            with self.subTest(title=title):
                self.assertEqual(parse_freq(f"{freq} {bw} {sf} {cr}"), (freq, bw, sf, cr))


class RadioCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = State(Path(self.enterContext(tempfile.TemporaryDirectory())))
        self.radio = FakeMeshCore()
        self.cmd = RadioCommand(make_context("radio", radio=self.radio, state=self.state, admins={ADMIN.public_key}))
        self.restarts = []
        self.state.restart = self.restarts.append
        self.rebooting = []  # what the node watch is told
        self.state.watch = mock.Mock(rebooting=self.rebooting.append)

    async def console(self, text):
        return await self.cmd.execute(text, CONSOLE)

    def history(self):
        return [(e["by"], e["what"]) for e in self.state.store(HISTORY_FILE).data.get("entries", [])]

    async def test_shows_the_settings(self):
        self.radio.clock = time.time() - 125
        self.radio.self_info.update(adv_lat=32.4487, adv_lon=-99.7331, adv_loc_policy=1)
        reply = (await self.cmd.execute("", ADMIN)).reply
        self.assertEqual(reply, "radio: test-node; 910.525 MHz BW62.5 SF7 CR5 (Canada, USA); TX 22/22 dBm; "
                                "position 32.44870, -99.73310 (in adverts); clock 2m behind; "
                                "firmware Test Board v1.9")

    async def test_shows_what_it_can(self):
        self.radio.self_info = {"name": "bare"}
        self.radio.commands.get_time = mock.AsyncMock(return_value=event(EventType.ERROR, {}))
        self.assertEqual((await self.cmd.execute("", ADMIN)).reply,
                         "radio: bare; no position; firmware Test Board v1.9")

    async def test_changes_only_from_the_console(self):
        for text in ["name Hilltop", "power 10", "reboot", "freq usa", "clock"]:
            with self.subTest(text=text), self.assertRaisesRegex(
                    CommandError, "^radio: changes only from the web console on the node's computer$"):
                await self.cmd.execute(text, ADMIN)
        self.assertEqual(self.radio.settings_calls, [])
        with self.assertRaisesRegex(CommandError, r"^usage: radio \["):
            await self.console("volume 11")

    async def test_name(self):
        done = await self.console("name Hilltop Relay")
        self.assertEqual(done.reply, "radio: name test-node -> Hilltop Relay; others see it after the next advert")
        self.assertEqual(self.radio.settings_calls, [("set_name", ("Hilltop Relay",))])
        self.assertEqual(self.history(), [("console", "radio: name test-node -> Hilltop Relay; others see it after "
                                                      "the next advert")])
        for text in ["name", "name " + "x" * 32, "name a\x07b"]:
            with self.subTest(text=text), self.assertRaises(CommandError):
                await self.console(text)

    async def test_power(self):
        self.assertEqual((await self.console("power 10")).reply, "radio: TX power 22 -> 10 dBm")
        self.assertEqual(self.radio.self_info["tx_power"], 10)
        for text, why in [("power 23", "1 to 22 dBm"), ("power 0", "1 to 22 dBm"), ("power lots", "usage")]:
            with self.subTest(text=text), self.assertRaisesRegex(CommandError, why):
                await self.console(text)

    async def test_position(self):
        self.assertEqual((await self.console("position 32.4487, -99.7331")).reply,
                         "radio: position 32.44870, -99.73310")
        self.assertEqual(self.radio.settings_calls, [("set_coords", (32.4487, -99.7331))])
        for text in ["position 91 0", "position 0 181", "position here", "position 1"]:
            with self.subTest(text=text), self.assertRaises(CommandError):
                await self.console(text)

    async def test_clock(self):
        with mock.patch("mesh_contingency.commands.radio.time.time", return_value=1_800_000_000.7):
            self.assertEqual((await self.console("clock")).reply, "radio: clock set from the computer")
        self.assertEqual(self.radio.settings_calls, [("set_time", (1_800_000_000,))])

    async def test_a_refusal_says_so(self):
        self.radio.settings_result = event(EventType.ERROR, {"reason": "bad"})
        with self.assertRaisesRegex(CommandError, "^radio: the radio didn't take the TX power: "):
            await self.console("power 10")
        self.assertEqual(self.history(), [])

    async def test_reboot_asks_then_restarts_the_bot(self):
        asked = await self.console("reboot")
        self.assertTrue(asked.asks)
        self.assertIn("this reboots the radio, and the bot restarts with it", asked.reply)
        self.assertEqual((self.radio.settings_calls, self.restarts), ([], []))
        done = await self.console("reboot")
        self.assertEqual(done.reply, "radio: rebooting; the bot restarts with it")
        self.assertEqual(self.radio.settings_calls, [("reboot", ())])
        self.assertEqual(self.restarts, ["the radio was rebooted from the console"])
        self.assertEqual(self.rebooting, self.restarts)  # so its restart isn't announced as a problem

    async def test_freq_asks_says_how_to_go_back_then_sets_and_reboots(self):
        asked = await self.console("freq australia (narrow)")
        self.assertTrue(asked.asks)
        self.assertEqual(asked.reply, "radio: this sets the radio to 916.575 MHz BW62.5 SF7 CR7 (Australia (Narrow)) "
                                      "and reboots it; the bot restarts with it. Radios on other settings won't hear "
                                      "this node. To go back, from the console: radio freq 910.525 62.5 7 5. Send it "
                                      "again within 5 min to confirm.")
        self.assertEqual(self.radio.settings_calls, [])
        # The same settings named another way confirm it.
        done = await self.console("freq 916.575 62.5 7 7")
        self.assertEqual(done.reply, "radio: set to 916.575 MHz BW62.5 SF7 CR7 (Australia (Narrow)) (was 910.525 MHz "
                                     "BW62.5 SF7 CR5); rebooting, and the bot restarts with it")
        self.assertEqual(self.radio.settings_calls, [("set_radio", (916.575, 62.5, 7, 7)), ("reboot", ())])
        self.assertEqual(self.restarts, ["the radio was set to 916.575 MHz BW62.5 SF7 CR7 from the console"])
        self.assertEqual(self.rebooting, self.restarts)

    async def test_freq_refused_doesnt_reboot(self):
        self.radio.settings_result = event(EventType.ERROR, {"reason": "bad"})
        await self.console("freq usa")
        with self.assertRaisesRegex(CommandError, "didn't take the settings"):
            await self.console("freq usa")
        self.assertEqual((self.restarts, self.rebooting), ([], []))
        self.assertNotIn(("reboot", ()), self.radio.settings_calls)

    async def test_freq_without_a_bot_to_restart_or_a_watch(self):
        self.state.restart = self.state.watch = None
        await self.console("freq usa")
        self.assertIn("rebooting", (await self.console("freq usa")).reply)


if __name__ == "__main__":
    unittest.main()
