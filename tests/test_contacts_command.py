import unittest
from types import SimpleNamespace

from mesh_contingency.api import MAX_PARTS, MAX_REPLY_LEN, CommandError, Sender, page
from mesh_contingency.commands.contacts import ContactsCommand
from mesh_contingency.testing import make_context

ADMIN = Sender("admin-node", "ad" * 32)
ALICE = "a1" * 32
HILLTOP = "37ca" + "00" * 30


def radio(*contacts):
    """A radio whose contacts are (name, key, type) tuples."""
    return SimpleNamespace(contacts={key: {"public_key": key, "adv_name": name, "type": kind}
                                     for name, key, kind in contacts})


class ContactsCommandTest(unittest.IsolatedAsyncioTestCase):
    def command(self, *contacts):
        return ContactsCommand(make_context("contacts", radio=radio(*contacts), users={ALICE: {"name": "Alice"}},
                                            admins={ADMIN.public_key}))

    async def test_lists_with_flags(self):
        cmd = self.command(("Hilltop", HILLTOP, 2), ("alice-node", ALICE, 1), ("Admin", ADMIN.public_key, 1),
                           ("", "ee" * 32, 1))
        self.assertEqual((await cmd.execute("", ADMIN)).reply,
                         [f"contacts (4): ? eeeeeeeeeeee Admin {ADMIN.public_key[:12]} (admin) "
                          f"alice-node a1a1a1a1a1a1 (user) Hilltop 37ca00000000 (repeater)"])

    async def test_filter_by_name_or_key(self):
        cmd = self.command(("Hilltop", HILLTOP, 2), ("alice-node", ALICE, 1), ("Alan", "a2" * 32, 1))
        self.assertEqual((await cmd.execute("al", ADMIN)).reply,
                         ["contacts matching al (2): Alan a2a2a2a2a2a2 alice-node a1a1a1a1a1a1 (user)"])
        self.assertEqual((await cmd.execute("37CA", ADMIN)).reply,
                         ["contacts matching 37CA (1): Hilltop 37ca00000000 (repeater)"])
        self.assertEqual((await cmd.execute("zed", ADMIN)).reply, "contacts: none matching zed")
        self.assertEqual((await self.command().execute("", ADMIN)).reply, "contacts: none")

    async def test_pages(self):
        cmd = self.command(*[(f"Node {i:03d}", f"{i:04x}" + "00" * 30, 1) for i in range(80)])
        first = (await cmd.execute("", ADMIN)).reply
        self.assertEqual(len(first), MAX_PARTS)
        self.assertTrue(all(len(m) <= MAX_REPLY_LEN for m in first))
        self.assertEqual(first[-1], "contacts: page 1 of 2; send contacts 2 for more")
        self.assertIn("Node 079", " ".join((await cmd.execute("2", ADMIN)).reply))
        with self.assertRaisesRegex(CommandError, r"^contacts: there are 2 page\(s\)$"):
            await cmd.execute("3", ADMIN)
        filtered = (await cmd.execute("node 1", ADMIN)).reply  # "node 1" + page 1, not a filter on "1"
        self.assertTrue(filtered[0].startswith("contacts matching node (80):"))


class PageTest(unittest.TestCase):
    def test_page(self):
        messages = [f"m{i}" for i in range(10)]
        self.assertEqual(page(messages, 1, "x"), [f"m{i}" for i in range(7)] + ["x: page 1 of 2; send x 2 for more"])
        self.assertEqual(page(messages, 2, "x", "x bob"), ["m7", "m8", "m9"])
        self.assertEqual(page(["only"], 1, "x"), ["only"])
        with self.assertRaisesRegex(CommandError, r"^x: there are 2 page\(s\)$"):
            page(messages, 0, "x")


if __name__ == "__main__":
    unittest.main()
