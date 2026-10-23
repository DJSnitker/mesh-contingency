"""The channel messages kept for the web console."""

import unittest
from unittest import mock

from meshcore import EventType

from mesh_contingency.alerts import post
from mesh_contingency.channel_log import ChannelLog, split_sender
from mesh_contingency.testing import FakeMeshCore, event


class SplitSenderTest(unittest.TestCase):
    def test_sender_and_message(self):
        self.assertEqual(split_sender("Alice: anyone on? 10:30"), ("Alice", "anyone on? 10:30"))
        self.assertEqual(split_sender("no sender here"), (None, "no sender here"))
        self.assertEqual(split_sender(": blank name"), (None, ": blank name"))
        self.assertEqual(split_sender("Net Control: at 7: bring water"), ("Net Control", "at 7: bring water"))


class ChannelLogTest(unittest.TestCase):
    def test_heard_newest_first_by_slot(self):
        log = ChannelLog()
        with mock.patch("mesh_contingency.channel_log.time.time", side_effect=[10.0, 20.0, 30.0]):
            log.heard({"channel_idx": 0, "text": "Bob: hi", "path_len": 255, "SNR": -3.25})
            log.heard({"channel_idx": 1, "text": "Alice: ok", "path_len": 3})
            log.heard({"channel_idx": 0, "text": "Carol: hello"})
        self.assertEqual(log.messages(0), [
            {"time": 30.0, "sender": "Carol", "text": "hello", "hops": None, "snr": None, "own": False},
            {"time": 10.0, "sender": "Bob", "text": "hi", "hops": 0, "snr": -3.25, "own": False}])  # 255: direct
        self.assertEqual([m["hops"] for m in log.messages(1)], [3])
        self.assertEqual((log.summary(0), log.summary(1), log.summary(2)), ((2, 30.0), (1, 20.0), (0, None)))
        self.assertEqual(log.messages(2), [])

    def test_keeps_only_the_newest(self):
        log = ChannelLog(keep=3)
        for n in range(5):
            log.heard({"channel_idx": 2, "text": f"Alice: {n}"})
        self.assertEqual([m["text"] for m in log.messages(2)], ["4", "3", "2"])

    def test_ignores_what_isnt_a_channel_message(self):
        log = ChannelLog()
        log.heard({"text": "Alice: no slot"})
        self.assertEqual(log.summary(0), (0, None))


class PostTest(unittest.IsolatedAsyncioTestCase):
    async def test_post_adds_what_it_sends(self):
        radio, log = FakeMeshCore(), ChannelLog()
        with mock.patch("mesh_contingency.alerts.asyncio.sleep"):
            await post(radio, 1, ["one", "two"], log)
        self.assertEqual([(m["sender"], m["text"], m["own"]) for m in log.messages(1)],
                         [("test-node", "two", True), ("test-node", "one", True)])

    async def test_a_refused_message_isnt_added(self):
        radio, log = FakeMeshCore(), ChannelLog()
        radio.channel_result = event(EventType.ERROR, {"reason": "busy"})
        with self.assertRaises(RuntimeError):
            await post(radio, 1, ["one"], log)
        self.assertEqual(log.messages(1), [])

    async def test_without_a_log(self):
        radio = FakeMeshCore()
        await post(radio, 1, ["one"])
        self.assertEqual(radio.channel_sent, [(1, "one")])


if __name__ == "__main__":
    unittest.main()
