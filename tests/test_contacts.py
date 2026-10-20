import contextlib
import io
import unittest

from meshcore import EventType

from mesh_contingency.contacts import NODE_TYPES, load_auto_add, setup_auto_add
from mesh_contingency.testing import FakeMeshCore, event, make_contact


class LoadAutoAddTest(unittest.TestCase):
    def test_not_configured(self):
        self.assertIsNone(load_auto_add({}))
        self.assertIsNone(load_auto_add({"contacts": {}}))

    def test_maps_names_to_types(self):
        self.assertEqual(load_auto_add({"contacts": {"auto_add": ["chat"]}}), {1})
        self.assertEqual(load_auto_add({"contacts": {"auto_add": list(NODE_TYPES)}}), {1, 2, 3, 4})
        self.assertEqual(load_auto_add({"contacts": {"auto_add": []}}), set())

    def test_unknown_type_exits(self):
        with self.assertRaisesRegex(SystemExit, "unknown type.*robot"):
            load_auto_add({"contacts": {"auto_add": ["chat", "robot"]}})


class SetupAutoAddTest(unittest.IsolatedAsyncioTestCase):
    async def setup(self, types=frozenset({1}), manual=False):
        radio = FakeMeshCore(manual_add_contacts=manual)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            await setup_auto_add(radio, set(types))
        return radio, out.getvalue()

    async def new_contact(self, radio, contact):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            await radio.deliver(EventType.NEW_CONTACT, contact)
        return out.getvalue()

    async def test_enables_manual_add_when_off(self):
        radio, out = await self.setup(manual=False)
        self.assertEqual(radio.manual_add_calls, [True])
        self.assertIn("Radio setting changed", out)
        self.assertIn("Auto-adding new contacts of type: chat", out)

    async def test_leaves_manual_add_alone_when_on(self):
        radio, out = await self.setup(manual=True)
        self.assertEqual(radio.manual_add_calls, [])
        self.assertNotIn("Radio setting changed", out)

    async def test_radio_refuses_manual_mode(self):
        radio = FakeMeshCore()
        radio.manual_add_result = event(EventType.ERROR, {"reason": "nope"})
        with self.assertRaisesRegex(SystemExit, "Could not enable manual contact adding"):
            with contextlib.redirect_stdout(io.StringIO()):
                await setup_auto_add(radio, {1})

    async def test_adds_listed_type_and_refreshes_contacts(self):
        radio, _ = await self.setup({1})
        out = await self.new_contact(radio, make_contact("a1a1a1a1a1a1", "Alice", 1))
        self.assertEqual([c["adv_name"] for c in radio.added], ["Alice"])
        self.assertEqual(radio.get_contacts_calls, 1)
        self.assertIsNotNone(radio.get_contact_by_key_prefix("a1a1a1a1a1a1"))
        self.assertIn("+ contact a1a1a1a1a1a1 Alice (chat)", out)

    async def test_skips_unlisted_types(self):
        radio, _ = await self.setup({1})
        out = await self.new_contact(radio, make_contact("b2b2b2b2b2b2", "Hilltop", 2))
        out += await self.new_contact(radio, make_contact("e5e5e5e5e5e5", "Odd", 9))
        self.assertEqual(radio.added, [])
        self.assertIn("skipped new contact b2b2b2b2b2b2 Hilltop (repeater)", out)
        self.assertIn("skipped new contact e5e5e5e5e5e5 Odd (9)", out)

    async def test_empty_list_adds_nothing(self):
        radio, out = await self.setup(set())
        self.assertIn("type: none", out)
        await self.new_contact(radio, make_contact("a1a1a1a1a1a1", "Alice", 1))
        self.assertEqual(radio.added, [])

    async def test_add_failure_is_logged(self):
        radio, _ = await self.setup({1})
        radio.add_contact_result = event(EventType.ERROR, {"error_code": 3})
        out = await self.new_contact(radio, make_contact("a1a1a1a1a1a1", "Alice", 1))
        self.assertIn("could not add contact a1a1a1a1a1a1 Alice (chat)", out)
        self.assertEqual(radio.get_contacts_calls, 0)


if __name__ == "__main__":
    unittest.main()
