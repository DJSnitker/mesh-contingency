import contextlib
import io
import unittest

from meshcore import EventType

from mesh_contingency.contacts import add_admins, contact_rows
from mesh_contingency.testing import FakeMeshCore, event, full_key, make_contact

ADMIN = "ad" * 32
LOOKALIKE = "ad" * 6 + "11" * 26  # the admin's key prefix, another key
STRANGER = "5e" * 32


class AddAdminsTest(unittest.IsolatedAsyncioTestCase):
    async def setup(self, manual=True):
        self.radio = FakeMeshCore(manual_add_contacts=manual)
        return await add_admins(self.radio, frozenset({ADMIN}))

    async def new_contact(self, contact):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            await self.radio.deliver(EventType.NEW_CONTACT, contact)
        return out.getvalue()

    async def test_the_radios_usual_mode_is_left_alone(self):
        self.assertIsNone(await self.setup(manual=False))
        self.assertNotIn(EventType.NEW_CONTACT, self.radio.handlers)
        self.assertEqual(self.radio.manual_add_calls, [])

    async def test_adds_an_admin_and_refreshes_contacts(self):
        self.assertIn("adding the admins' radios", await self.setup())
        out = await self.new_contact(make_contact(ADMIN, "Admin"))
        self.assertEqual([c["public_key"] for c in self.radio.added], [ADMIN])
        self.assertEqual(self.radio.get_contacts_calls, 1)
        self.assertEqual(out, "+ admin contact adadadadadad Admin\n")
        self.assertEqual(self.radio.manual_add_calls, [])  # the radio's setting is never changed

    async def test_others_are_not_added(self):
        await self.setup()
        for node_type in (1, 2):
            self.assertEqual(await self.new_contact(make_contact(STRANGER, "Stranger", node_type)), "")
        self.assertEqual(self.radio.added, [])

    async def test_a_lookalike_of_an_admin_is_reported_once(self):
        await self.setup()
        out = await self.new_contact(make_contact(LOOKALIKE, "Admin"))
        out += await self.new_contact(make_contact(LOOKALIKE, "Admin"))  # advertising again
        self.assertEqual(self.radio.added, [])
        self.assertEqual(out.count("! not adding adadadadadad Admin: same key prefix as an admin"), 1)
        self.assertNotIn(LOOKALIKE, out)  # no full keys in the log

    async def test_add_failure_is_logged(self):
        await self.setup()
        self.radio.add_contact_result = event(EventType.ERROR, {"reason": "table full"})
        out = await self.new_contact(make_contact(ADMIN, "Admin"))
        self.assertIn("could not add admin adadadadadad Admin", out)


class ContactRowsTest(unittest.TestCase):
    def test_sorted_and_filtered(self):
        radio = FakeMeshCore({"bb" * 6: "bob", "aa" * 6: "Alice", "cc" * 6: ""})
        self.assertEqual(contact_rows(radio), [("?", full_key("cc" * 6), "chat"), ("Alice", full_key("aa" * 6), "chat"),
                                               ("bob", full_key("bb" * 6), "chat")])
        self.assertEqual([r[0] for r in contact_rows(radio, "B")], ["bob"])
        self.assertEqual([r[0] for r in contact_rows(radio, "aaaa")], ["Alice"])


if __name__ == "__main__":
    unittest.main()
