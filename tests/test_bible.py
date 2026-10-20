import contextlib
import gzip
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mesh_contingency import bible
from mesh_contingency.bible import Bible, Passage, default_bible, normalize
from mesh_contingency.bible import build
from mesh_contingency.bible.votd import VERSES, reference_for


def source_verse(number, text):
    return {"type": "verse", "number": number, "text": text, "footnotes": []}


def source_book(book_id, name, chapters):
    """A book shaped like helloao's complete.simple.json."""
    return {"id": book_id, "commonName": name, "chapters": [
        {"chapter": {"number": i, "content": [{"type": "heading", "text": "A Heading"}, *verses,
                                              {"type": "line_break"}]}}
        for i, verses in enumerate(chapters, 1)]}


SOURCE = {
    "translation": {"shortName": "BSB"},
    "books": [
        source_book("GEN", "Genesis", [[source_verse(1, "In the beginning."), source_verse(2, "Second.")],
                                       [source_verse(1, "Chapter two.")]]),
        source_book("PSA", "Psalms", [[source_verse(1, "The LORD is my shepherd;\nI shall not want.")]]),
        source_book("MAT", "Matthew", [[source_verse(1, "One."), source_verse(3, "Three.")]]),  # 2 omitted
        source_book("JOB", "Job", [[source_verse(1, "Job one.")], [source_verse(1, "Job two.")]]),
        source_book("JHN", "John", [[source_verse(1, "John one.")], [source_verse(1, "John two.")]]),
        source_book("1JN", "1 John", [[source_verse(1, "First John.")], [source_verse(1, "x")]]),
        source_book("JUD", "Jude", [[source_verse(1, "Jude one."), source_verse(2, "Jude two.")]]),
        source_book("JDG", "Judges", [[source_verse(1, "Judges one.")], [source_verse(1, "x")]]),
        source_book("PHP", "Philippians", [[source_verse(1, "Phil one.")], [source_verse(1, "x")]]),
        source_book("PHM", "Philemon", [[source_verse(1, "Philemon one.")]]),
    ],
}


class CleanTest(unittest.TestCase):
    def test_typographic_characters_become_ascii(self):
        self.assertEqual(build.clean("“God’s ‘word’…” 1–2"),
                         "\"God's 'word'...\" 1-2")

    def test_lines_joined(self):
        self.assertEqual(build.clean(" The LORD is my shepherd;\nI shall not want. "),
                         "The LORD is my shepherd; I shall not want.")

    def test_em_dashes_closed_up(self):
        self.assertEqual(build.clean("my prayer—\nit comes"), "my prayer--it comes")
        self.assertEqual(build.clean("High —and"), "High--and")

    def test_space_before_closing_punctuation_removed(self):
        self.assertEqual(build.clean("(the Salt Sea ). heel.\n” ok ,"), "(the Salt Sea). heel.\" ok,")

    def test_unexpected_character_rejected(self):
        with self.assertRaisesRegex(ValueError, "unexpected characters"):
            build.clean("café")
        with self.assertRaises(ValueError):
            build.clean("tab\x00null")


class ConvertTest(unittest.TestCase):
    def test_compact_form(self):
        data = build.convert(SOURCE)
        self.assertEqual(data["translation"], "BSB")
        genesis = data["books"][0]
        self.assertEqual(genesis, {"id": "GEN", "name": "Genesis",
                                   "chapters": [["In the beginning.", "Second."], ["Chapter two."]]})
        self.assertEqual(data["books"][1]["chapters"], [["The LORD is my shepherd; I shall not want."]])

    def test_omitted_verse_kept_as_empty_slot(self):
        self.assertEqual(build.convert(SOURCE)["books"][2]["chapters"], [["One.", "", "Three."]])


class BuildMainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out_file = Path(tmp.name) / "bsb.json.gz"
        self.source_file = Path(tmp.name) / "complete.simple.json"
        self.source_file.write_text(json.dumps(SOURCE))
        self.enterContext(mock.patch("mesh_contingency.bible.build.DATA_FILE", self.out_file))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def run_build(self, *args):
        with mock.patch("sys.argv", ["build.py", *args]):
            build.main()
        return self.out_file.read_bytes()

    def test_from_local_source(self):
        written = self.run_build("--source", str(self.source_file))
        self.assertEqual(json.loads(gzip.decompress(written)), build.convert(SOURCE))
        # Identical input gives an identical file (no timestamp in the gzip header).
        self.assertEqual(self.run_build("--source", str(self.source_file)), written)

    def test_downloads_by_default(self):
        response = io.BytesIO(json.dumps(SOURCE).encode())
        with mock.patch("mesh_contingency.bible.build.urllib.request.urlopen", return_value=response) as urlopen:
            written = self.run_build()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, build.SOURCE_URL)
        self.assertEqual(request.get_header("User-agent"), build.USER_AGENT)
        self.assertEqual(json.loads(gzip.decompress(written))["books"][0]["id"], "GEN")


class NormalizeTest(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(normalize("Song of Solomon"), "songofsolomon")
        self.assertEqual(normalize(" 1 John "), "1john")
        self.assertEqual(normalize("I John"), "1john")
        self.assertEqual(normalize("ii kings"), "2kings")
        self.assertEqual(normalize("Third John"), "3john")
        self.assertEqual(normalize("1st Pet."), "1pet")
        self.assertEqual(normalize("Isaiah"), "isaiah")  # a leading "i" in a word is not an ordinal


class FindBookTest(unittest.TestCase):
    def setUp(self):
        self.bible = Bible(build.convert(SOURCE))

    def find(self, name):
        return self.bible.find_book(name)["id"]

    def test_full_name_id_and_alias(self):
        self.assertEqual(self.find("Genesis"), "GEN")
        self.assertEqual(self.find("jhn"), "JHN")
        self.assertEqual(self.find("jn"), "JHN")
        self.assertEqual(self.find("psalm"), "PSA")
        self.assertEqual(self.find("1 jn"), "1JN")
        self.assertEqual(self.find("I John"), "1JN")
        self.assertEqual(self.find("phil"), "PHP")  # alias wins over the Philemon prefix
        self.assertEqual(self.find("jud"), "JUD")  # Jude's id, not a prefix of Judges

    def test_unambiguous_prefix(self):
        self.assertEqual(self.find("gen"), "GEN")
        self.assertEqual(self.find("matt"), "MAT")
        self.assertEqual(self.find("philem"), "PHM")

    def test_ambiguous_prefix(self):
        with self.assertRaisesRegex(ValueError, "'jo' could be Job, John"):
            self.find("jo")

    def test_unknown(self):
        with self.assertRaisesRegex(ValueError, "unknown book 'xyz'"):
            self.find("xyz")
        with self.assertRaisesRegex(ValueError, "unknown book 'g'"):
            self.find("g")  # one letter is too short to match by prefix


class LookupTest(unittest.TestCase):
    def setUp(self):
        self.bible = Bible(build.convert(SOURCE))

    def lookup(self, reference):
        return self.bible.lookup(reference)

    def test_single_verse(self):
        self.assertEqual(self.lookup("gen 1:1"), Passage("Genesis 1:1", [(1, "In the beginning.")]))
        self.assertEqual(self.lookup("  Genesis 2 : 1 ").reference, "Genesis 2:1")
        self.assertEqual(self.lookup("gen 1.2").text, "Second.")

    def test_range_numbers_later_verses(self):
        passage = self.lookup("gen 1:1-2")
        self.assertEqual(passage.reference, "Genesis 1:1-2")
        self.assertEqual(passage.text, "In the beginning. 2 Second.")
        self.assertEqual(self.lookup("gen 1:1 – 2").reference, "Genesis 1:1-2")
        self.assertEqual(self.lookup("gen 1:1-1").reference, "Genesis 1:1")

    def test_psalm_singular(self):
        self.assertEqual(self.lookup("ps 1:1").reference, "Psalm 1:1")

    def test_numbered_book(self):
        self.assertEqual(self.lookup("1 John 1:1").text, "First John.")
        self.assertEqual(self.lookup("1jn1:1").text, "First John.")

    def test_single_chapter_book_by_verse_alone(self):
        self.assertEqual(self.lookup("jude 2"), Passage("Jude 1:2", [(2, "Jude two.")]))
        self.assertEqual(self.lookup("jude 1:2").reference, "Jude 1:2")

    def test_multi_chapter_book_needs_a_verse(self):
        with self.assertRaisesRegex(ValueError, "which verse\\? e.g. Genesis 2:1"):
            self.lookup("gen 2")

    def test_out_of_range(self):
        with self.assertRaisesRegex(ValueError, "Genesis has 2 chapters"):
            self.lookup("gen 3:1")
        with self.assertRaisesRegex(ValueError, "Genesis has 2 chapters"):
            self.lookup("gen 0:1")
        with self.assertRaisesRegex(ValueError, "Genesis 1 has 2 verses"):
            self.lookup("gen 1:3")
        with self.assertRaisesRegex(ValueError, "Genesis 1 has 2 verses"):
            self.lookup("gen 1:1-5")
        with self.assertRaisesRegex(ValueError, "Genesis 1 has 2 verses"):
            self.lookup("gen 1:0")
        with self.assertRaisesRegex(ValueError, "Jude 1 has 2 verses"):
            self.lookup("jude 3")

    def test_backwards_range(self):
        with self.assertRaisesRegex(ValueError, "backwards range 2-1"):
            self.lookup("gen 1:2-1")

    def test_omitted_verse(self):
        with self.assertRaisesRegex(ValueError, "Matthew 1:2 is not in the BSB text"):
            self.lookup("matt 1:2")
        self.assertEqual(self.lookup("matt 1:1-3").text, "One. 3 Three.")

    def test_not_a_reference(self):
        for text in ("", "hello", "3:16", "john", "john 3:16 and more"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.lookup(text)


class BundledBibleTest(unittest.TestCase):
    """Checks on the real bible/bsb.json.gz shipped with the bot."""

    @classmethod
    def setUpClass(cls):
        cls.bible = default_bible()

    def test_cached(self):
        self.assertIs(default_bible(), self.bible)
        self.assertEqual(bible.DATA_FILE.name, "bsb.json.gz")

    def test_complete(self):
        self.assertEqual(self.bible.translation, "BSB")
        self.assertEqual(len(self.bible.books), 66)
        verses = [v for b in self.bible.books for c in b["chapters"] for v in c if v]
        self.assertEqual(len(verses), 31086)
        self.assertEqual(sum(len(b["chapters"]) for b in self.bible.books), 1189)

    def test_plain_ascii(self):
        for book in self.bible.books:
            for chapter in book["chapters"]:
                for verse in chapter:
                    self.assertTrue(all(" " <= c <= "~" for c in verse), verse)

    def test_known_verses(self):
        self.assertEqual(self.bible.lookup("john 3:16").text,
                         "For God so loved the world that He gave His one and only Son, that everyone "
                         "who believes in Him shall not perish but have eternal life.")
        self.assertEqual(self.bible.lookup("ps 23:1").text, "The LORD is my shepherd; I shall not want.")
        self.assertEqual(self.bible.lookup("rev 22:21").reference, "Revelation 22:21")
        with self.assertRaisesRegex(ValueError, "not in the BSB text"):
            self.bible.lookup("matt 17:21")

    def test_every_book_reachable_by_name_and_id(self):
        for book in self.bible.books:
            self.assertIs(self.bible.find_book(book["name"]), book)
            self.assertIs(self.bible.find_book(book["id"]), book)

    def test_aliases_name_real_books(self):
        ids = {b["id"] for b in self.bible.books}
        self.assertLessEqual(set(bible.ALIASES) | set(bible.DISPLAY_NAMES), ids)
        for book_id, aliases in bible.ALIASES.items():
            for alias in aliases:
                self.assertEqual(self.bible.find_book(alias)["id"], book_id, alias)


class VerseOfTheDayTest(unittest.TestCase):
    def test_every_reference_resolves(self):
        bible = default_bible()
        self.assertEqual(len(VERSES), len(set(VERSES)))
        for reference in VERSES:
            self.assertEqual(bible.lookup(reference).reference.replace("Jude 1:", "Jude "), reference)

    def test_one_per_day_in_turn(self):
        import datetime
        day = datetime.date(2026, 10, 19)
        self.assertEqual(reference_for(day), reference_for(datetime.date(2026, 10, 19)))
        days = [reference_for(day + datetime.timedelta(n)) for n in range(len(VERSES))]
        self.assertEqual(sorted(days), sorted(VERSES))


if __name__ == "__main__":
    unittest.main()
