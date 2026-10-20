import contextlib
import io
import unittest

from meshcore import EventType

from mesh_contingency.contacts import NODE_TYPES, load_auto_add, load_notify_admins, lookalike_of, setup_auto_add
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


class LoadNotifyAdminsTest(unittest.TestCase):
    def test_default_on(self):
        self.assertTrue(load_notify_admins({}))
        self.assertTrue(load_notify_admins({"contacts": {"auto_add": ["chat"]}}))

    def test_setting(self):
        self.assertTrue(load_notify_admins({"contacts": {"notify_admins": True}}))
        self.assertFalse(load_notify_admins({"contacts": {"notify_admins": False}}))

    def test_must_be_boolean(self):
        for value in ("no", 0, "false"):
            with self.subTest(value=value), self.assertRaisesRegex(SystemExit, "must be true or false"):
                load_notify_admins({"contacts": {"notify_admins": value}})


DANA = "d0" * 32  # a protected user's full key
LOOKALIKE = "d0" * 6 + "11" * 26  # same prefix, different key


class LookalikeTest(unittest.TestCase):
    def test_same_prefix_different_key(self):
        self.assertEqual(lookalike_of(LOOKALIKE, {DANA, "ad" * 32}), DANA)
        self.assertEqual(lookalike_of(LOOKALIKE.upper(), {DANA}), DANA)

    def test_the_real_key_or_another_prefix(self):
        self.assertIsNone(lookalike_of(DANA, {DANA}))
        self.assertIsNone(lookalike_of("ab" * 32, {DANA}))
        self.assertIsNone(lookalike_of(LOOKALIKE, set()))


class SetupAutoAddTest(unittest.IsolatedAsyncioTestCase):
    async def setup(self, types=frozenset({1}), manual=False):
        radio = FakeMeshCore(manual_add_contacts=manual)
        self.added = []  # on_added calls
        self.blocked = []  # on_blocked calls
        self.protected = {DANA}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            await setup_auto_add(radio, set(types), on_added=lambda *args: self.added.append(args),
                                 protected=lambda: self.protected, on_blocked=lambda *args: self.blocked.append(args))
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
        self.assertEqual(self.added, [("a1a1a1a1a1a1", "Alice", "chat")])

    async def test_on_added_with_unnamed_node(self):
        radio, _ = await self.setup({1, 3})
        await self.new_contact(radio, make_contact("a1a1a1a1a1a1", "", 3))
        self.assertEqual(self.added, [("a1a1a1a1a1a1", "", "room")])

    async def test_on_added_is_optional(self):
        radio = FakeMeshCore()
        with contextlib.redirect_stdout(io.StringIO()):
            await setup_auto_add(radio, {1})
        await self.new_contact(radio, make_contact("a1a1a1a1a1a1", "Alice", 1))
        self.assertEqual(len(radio.added), 1)

    async def test_skips_unlisted_types(self):
        radio, _ = await self.setup({1})
        out = await self.new_contact(radio, make_contact("b2b2b2b2b2b2", "Hilltop", 2))
        out += await self.new_contact(radio, make_contact("e5e5e5e5e5e5", "Odd", 9))
        self.assertEqual(radio.added, [])
        self.assertIn("skipped new contact b2b2b2b2b2b2 Hilltop (repeater)", out)
        self.assertIn("skipped new contact e5e5e5e5e5e5 Odd (9)", out)
        self.assertEqual(self.added, [])  # nothing announced for skipped nodes

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
        self.assertEqual(self.added, [])  # nor for nodes the radio refused


    async def test_lookalike_of_a_user_is_blocked_once(self):
        radio, _ = await self.setup({1})
        out = await self.new_contact(radio, make_contact(LOOKALIKE, "Dana", 1))
        out += await self.new_contact(radio, make_contact(LOOKALIKE, "Dana", 1))  # advertising again
        self.assertEqual(radio.added, [])
        self.assertEqual(self.added, [])
        self.assertEqual(self.blocked, [("d0d0d0d0d0d0", "Dana", DANA)])
        self.assertEqual(out.count("! blocked new contact d0d0d0d0d0d0 Dana (chat)"), 1)
        self.assertNotIn(LOOKALIKE, out)  # no full keys in the log

    async def test_the_user_themselves_is_added(self):
        radio, _ = await self.setup({1})
        await self.new_contact(radio, make_contact(DANA, "Dana", 1))
        self.assertEqual(len(radio.added), 1)
        self.assertEqual(self.blocked, [])

    async def test_protected_keys_read_each_time(self):
        radio, _ = await self.setup({1})
        self.protected = set()  # Dana removed from the users file
        await self.new_contact(radio, make_contact(LOOKALIKE, "Other", 1))
        self.assertEqual(len(radio.added), 1)

    async def test_lookalike_of_unlisted_type_just_skipped(self):
        radio, _ = await self.setup({1})
        out = await self.new_contact(radio, make_contact(LOOKALIKE, "Hilltop", 2))
        self.assertIn("skipped new contact", out)
        self.assertEqual(self.blocked, [])


if __name__ == "__main__":
    unittest.main()
