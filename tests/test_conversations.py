import unittest

from mesh_contingency.conversations import REPLY_HOURS, Conversations

KEY = "ab" * 32


class ConversationsTest(unittest.TestCase):
    def test_keeps_the_consoles_messages_and_the_replies(self):
        kept = Conversations()
        entry = kept.sent(KEY, "net at 7?", when=100.0)
        self.assertEqual(entry["status"], "sending")
        kept.delivered(entry, True)
        kept.replied(KEY, "yes", hops=255, snr=6.5, when=160.0)
        self.assertEqual([(m["text"], m["own"], m["status"], m["hops"]) for m in kept.messages(KEY)],
                         [("yes", False, None, 0), ("net at 7?", True, "delivered", None)])
        self.assertEqual(kept.heard_count(KEY), 1)
        self.assertEqual(kept.last(KEY)["text"], "yes")
        self.assertEqual(kept.messages("cd" * 32), [])
        self.assertIsNone(kept.last("cd" * 32))

    def test_a_message_not_delivered(self):
        kept = Conversations()
        entry = kept.sent(KEY, "hello")
        kept.delivered(entry, False)
        self.assertEqual(kept.messages(KEY)[0]["status"], "not delivered")

    def test_expects_replies_only_for_a_while_after_messaging(self):
        kept = Conversations()
        self.assertFalse(kept.expecting(KEY, now=100.0))
        kept.sent(KEY, "hello", when=100.0)
        self.assertTrue(kept.expecting(KEY, now=100.0 + REPLY_HOURS * 3600))
        self.assertFalse(kept.expecting(KEY, now=101.0 + REPLY_HOURS * 3600))

    def test_keeps_the_newest_and_lists_the_latest_conversation_first(self):
        kept = Conversations(keep=2)
        for n in range(3):
            kept.replied(KEY, str(n), when=float(n))
        kept.sent("cd" * 32, "hi", when=10.0)
        self.assertEqual([m["text"] for m in kept.messages(KEY)], ["2", "1"])
        self.assertEqual(kept.heard_count(KEY), 3)
        self.assertEqual(kept.keys(), ["cd" * 32, KEY])

    def test_what_it_hands_out_is_a_copy(self):
        kept = Conversations()
        kept.sent(KEY, "hello")
        kept.messages(KEY)[0]["text"] = "changed"
        self.assertEqual(kept.messages(KEY)[0]["text"], "hello")
