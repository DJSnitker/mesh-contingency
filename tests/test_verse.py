import datetime
import unittest

from mesh_contingency.bible import Bible, default_bible
from mesh_contingency.bible.votd import reference_for
from mesh_contingency.api import MAX_REPLY_LEN, CommandError, Sender
from mesh_contingency.commands.verse import MAX_PARTS, VerseCommand
from mesh_contingency.testing import make_context

DANA = Sender("Dana", "d0d0d0d0d0d0")
TODAY = datetime.date(2026, 10, 19)


class VerseCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cmd = VerseCommand(make_context("verse"), today=lambda: TODAY)

    def test_name(self):
        self.assertEqual(self.cmd.usage, "verse [book chapter:verse[-verse]]")

    async def test_short_verse_is_one_message(self):
        result = await self.cmd.execute("phil 4:13", DANA)
        self.assertEqual(result.reply, ["Philippians 4:13 I can do all things through Christ who gives me strength."])
        self.assertEqual(result.console, "Philippians 4:13 (BSB)\n"
                                         "  I can do all things through Christ who gives me strength.")

    async def test_long_verse_is_numbered_parts(self):
        result = await self.cmd.execute("john 3:16", DANA)
        self.assertEqual(result.reply, [
            "(1/2) John 3:16 For God so loved the world that He gave His one and only Son, that everyone "
            "who believes in Him shall not perish but",
            "(2/2) have eternal life.",
        ])
        self.assertIn("eternal life.", result.console)

    async def test_longest_verse(self):
        result = await self.cmd.execute("2 kings 16:15", DANA)
        self.assertEqual(len(result.reply), 4)
        self.assertTrue(all(len(part) <= MAX_REPLY_LEN for part in result.reply))
        self.assertTrue(result.reply[3].startswith("(4/4) "))

    async def test_verse_of_the_day(self):
        result = await self.cmd.execute("", DANA)
        reference = default_bible().lookup(reference_for(TODAY)).reference
        self.assertTrue(result.console.startswith(f"Verse of the day: {reference} (BSB)\n"))
        self.assertIn(reference, result.reply[0])

    async def test_too_many_messages(self):
        with self.assertRaisesRegex(CommandError, rf"verse: Psalm 119:1-20 needs \d+ messages, max {MAX_PARTS}"):
            await self.cmd.execute("ps 119:1-20", DANA)
        result = await self.cmd.execute("ps 119:1-8", DANA)  # 5 messages
        self.assertLessEqual(len(result.reply), MAX_PARTS)

    async def test_bad_reference(self):
        with self.assertRaisesRegex(CommandError, "verse: unknown book 'nowhere'"):
            await self.cmd.execute("nowhere 1:1", DANA)
        with self.assertRaisesRegex(CommandError, r"verse: try e.g. john 3:16"):
            await self.cmd.execute("john", DANA)

    async def test_bible_loaded_on_first_use(self):
        calls = []
        data = {"translation": "BSB", "books": [{"id": "GEN", "name": "Genesis", "chapters": [["Hi."]]}]}

        def load():
            calls.append(1)
            return Bible(data)

        cmd = VerseCommand(make_context("verse"), load=load)
        self.assertEqual(calls, [])
        self.assertEqual((await cmd.execute("gen 1:1", DANA)).reply, ["Genesis 1:1 Hi."])
        self.assertEqual(calls, [1])

    def test_defaults(self):
        cmd = VerseCommand(make_context("verse"))
        self.assertIs(cmd.load, default_bible)
        self.assertEqual(cmd.today, datetime.date.today)


if __name__ == "__main__":
    unittest.main()
