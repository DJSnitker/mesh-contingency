"""contact remove|path: managing one of the radio's contacts, and finding it."""

import tempfile
import unittest
from pathlib import Path

from meshcore import EventType

from mesh_contingency.api import CommandError, Sender
from mesh_contingency.commands.contact import ContactCommand
from mesh_contingency.contacts import ContactNotFound, find_contact
from mesh_contingency.state import HISTORY_FILE, State
from mesh_contingency.testing import FakeMeshCore, event, full_key, make_context

ADMIN = Sender("Net Control", "ad" * 32)
ALICE = "a1" * 32
HILLTOP = full_key("37ca5e")


class FindContactTest(unittest.TestCase):
    def setUp(self):
        self.radio = FakeMeshCore({"a1" * 32: "alice-node", "37ca5e": "Hilltop", "37cb01": "Hilltop Ridge",
                                   "b0" * 32: "Bob"})

    def find(self, text):
        return find_contact(self.radio, text)["adv_name"]

    def test_by_name_key_or_the_start_of_either(self):
        self.assertEqual(self.find("HILLTOP"), "Hilltop")  # a whole name wins over its start
        self.assertEqual(self.find("37ca"), "Hilltop")
        self.assertEqual(self.find(HILLTOP.upper()), "Hilltop")
        self.assertEqual(self.find("hilltop r"), "Hilltop Ridge")
        self.assertEqual(self.find("  bo "), "Bob")

    def test_none_or_several(self):
        self.assertEqual(self.find("37cb0"), "Hilltop Ridge")
        for text, message in [("", "give a name or key"), ("zed", "no contact zed"),
                              ("37c", "no contact 37c")]:  # too short for a key, and no name starts so
            with self.subTest(text=text), self.assertRaisesRegex(ContactNotFound, f"^{message}$"):
                find_contact(self.radio, text)
        self.radio.known["c0" * 32] = "Bob"
        with self.assertRaisesRegex(ContactNotFound, "^2 contacts match bob; give more of the key$"):
            find_contact(self.radio, "bob")
        self.radio.known["37ca99"] = "Other"
        with self.assertRaisesRegex(ContactNotFound, "^2 contacts match 37ca; give more of the key$"):
            find_contact(self.radio, "37ca")


class ContactCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.state = State(self.folder)
        self.radio = FakeMeshCore({"a1" * 32: "alice-node", "37ca5e": "Hilltop", ADMIN.public_key: "Net Control"})
        self.cmd = ContactCommand(make_context("contact", radio=self.radio, state=self.state,
                                               users={ALICE: {"name": "Alice"}}, admins={ADMIN.public_key}))

    async def run_it(self, text):
        return await self.cmd.execute(text, ADMIN)

    def history(self):
        return [entry["what"] for entry in self.state.store(HISTORY_FILE).data.get("entries", [])]

    async def test_usage(self):
        for text in ["", "remove", "delete Hilltop", "path  "]:
            with self.subTest(text=text), self.assertRaisesRegex(CommandError, r"^usage: contact remove\|path "):
                await self.run_it(text)

    async def test_remove_asks_then_removes(self):
        asked = await self.run_it("remove Hilltop")
        self.assertTrue(asked.asks)
        self.assertEqual(asked.reply, "contact: this removes Hilltop (37ca5e000000) from the radio. Send it again "
                                      "within 5 min to confirm.")
        self.assertEqual(self.radio.removed, [])
        done = await self.run_it("REMOVE 37ca")  # the same contact, named another way
        self.assertFalse(done.asks)
        self.assertEqual(done.reply, "contact: Hilltop (37ca5e000000) removed from the radio")
        self.assertEqual(self.radio.removed, [HILLTOP])
        self.assertNotIn(HILLTOP, self.radio.contacts)
        self.assertEqual(self.history(), ["removed contact Hilltop (37ca5e000000) from the radio"])

    async def test_says_when_its_one_of_the_nodes_people(self):
        self.assertIn("(a1a1a1a1a1a1, a user) from the radio. They can't be messaged until they advert again.",
                      (await self.run_it("remove alice")).reply)
        self.assertIn("(adadadadadad, an admin)", (await self.run_it("remove net control")).reply)

    async def test_asking_about_another_starts_over(self):
        await self.run_it("remove Hilltop")
        await self.run_it("remove alice-node")
        self.assertTrue((await self.run_it("remove Hilltop")).asks)
        self.assertEqual(self.radio.removed, [])

    async def test_a_refusal_says_so_and_keeps_the_contact(self):
        self.radio.remove_contact_result = event(EventType.ERROR, {"reason": "not found"})
        await self.run_it("remove Hilltop")
        with self.assertRaisesRegex(CommandError, "^contact: the radio didn't remove Hilltop: "):
            await self.run_it("remove Hilltop")
        self.assertIn(HILLTOP, self.radio.contacts)
        self.assertEqual(self.history(), [])

    async def test_reset_the_path(self):
        done = await self.run_it("path hilltop")
        self.assertEqual(done.reply, "contact: path to Hilltop (37ca5e000000) reset; the next message to it floods")
        self.assertEqual(self.radio.paths_reset, [HILLTOP])
        self.assertEqual(self.history(), ["reset the path to contact Hilltop (37ca5e000000)"])
        self.radio.reset_path_result = event(EventType.ERROR, {"reason": "x"})
        with self.assertRaisesRegex(CommandError, "^contact: the radio didn't reset the path to Hilltop: "):
            await self.run_it("path hilltop")

    async def test_no_such_contact(self):
        with self.assertRaisesRegex(CommandError, "^contact: no contact zed$"):
            await self.run_it("remove zed")


if __name__ == "__main__":
    unittest.main()
