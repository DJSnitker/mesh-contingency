import asyncio
import contextlib
import io
import unittest

from mesh_commands import KeyRoles, MeshLink, Sender
from mesh_commands.replies import MAX_REPLY_LEN
from mesh_commands.testing import FakeMeshCore, full_key
from meshcore import EventType

ADMIN_KEY, DANA = "adadadadadad", "d0d0d0d0d0d0"


class MeshLinkTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.out = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.radio = FakeMeshCore({ADMIN_KEY: "Admin", DANA: "Dana"})
        self.link = MeshLink(self.radio, KeyRoles(admins={full_key(ADMIN_KEY)}))

    async def test_sender_is_the_one_contact_with_the_prefix(self):
        self.assertEqual(await self.link.sender_of(DANA), Sender("Dana", full_key(DANA)))

    async def test_a_new_contact_is_looked_up(self):
        self.radio.stored[full_key("c0ffeec0ffee")] = "Late"
        self.assertEqual(await self.link.sender_of("c0ffeec0ffee"), Sender("Late", full_key("c0ffeec0ffee")))
        self.assertEqual(self.radio.get_contacts_calls, 1)

    async def test_unknown_and_shared_prefixes_identify_nobody(self):
        self.assertEqual(await self.link.sender_of("123456789abc"), Sender("123456789abc", None))
        self.radio.known[ADMIN_KEY + "11" * 26] = "Admin"  # an impostor
        self.assertEqual(await self.link.sender_of(ADMIN_KEY), Sender(ADMIN_KEY, None))
        self.assertIn(f"(2 contacts share key prefix {ADMIN_KEY}; sender not identified; one is an admin, so "
                      "remove the impostor from the radio)", self.out.getvalue())

    async def test_send_logs_delivery(self):
        await self.link.send(full_key(DANA), "hello")
        self.assertEqual(self.radio.sent, [("Dana", "hello")])
        self.assertIn(f"(reply to {DANA} delivered)", self.out.getvalue())
        self.radio.ack_result = None
        await self.link.send(full_key(DANA), "again", what="notice")
        self.assertIn(f"(notice to {DANA} not acknowledged after retries)", self.out.getvalue())

    async def test_send_to_no_contact(self):
        await self.link.send("c0ffeec0ffee", "hello")
        self.assertEqual(self.radio.sent, [])
        self.assertIn("(no contact c0ffeec0ffee to send reply to", self.out.getvalue())

    async def test_long_text_is_cut(self):
        await self.link.send(DANA, "x" * 500)
        (_, text), = self.radio.sent
        self.assertEqual(len(text), MAX_REPLY_LEN)
        self.assertTrue(text.endswith("..."))

    async def test_sends_never_overlap(self):
        active = peak = 0
        original = self.radio.commands.send_msg_with_retry

        async def slow(contact, text):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return await original(contact, text)

        self.radio.commands.send_msg_with_retry = slow
        for i in range(3):
            self.link.send_later(DANA, f"m{i}")
        await self.link.send(DANA, "reply")
        while len(self.radio.sent) < 4:
            await asyncio.sleep(0.01)
        self.assertEqual(peak, 1)

    async def test_listen_hands_messages_over(self):
        heard = []

        class Recorder:
            async def handle(self, prefix, sender, text):
                heard.append((prefix, sender, text))

        self.link.listen(Recorder())
        self.assertEqual(set(self.radio.handlers), {EventType.CONTACT_MSG_RECV})
        await self.radio.dm(DANA.upper(), "help")
        self.assertEqual(heard, [(DANA, Sender("Dana", full_key(DANA)), "help")])


if __name__ == "__main__":
    unittest.main()
