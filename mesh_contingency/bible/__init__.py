"""Offline Berean Standard Bible: reference parsing and verse lookup.

The text is bundled in bsb.json.gz (built by build.py), so lookups need
no network. The BSB is public domain and needs no attribution.
"""

import functools
import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path

DATA_FILE = Path(__file__).with_name("bsb.json.gz")

# Common abbreviations, beyond each book's full name, USFM id (GEN, JHN, ...)
# and any unambiguous prefix of its name, which are all accepted anyway.
ALIASES = {
    "GEN": ["gn"], "LEV": ["lv"], "NUM": ["nm", "nb"], "DEU": ["dt"], "JDG": ["jdgs"],
    "RUT": ["rth"], "1SA": ["1sm"], "2SA": ["2sm"], "1KI": ["1kgs"], "2KI": ["2kgs"],
    "JOB": ["jb"], "PSA": ["psalm", "psm", "pss"], "PRO": ["prv"], "ECC": ["qoh", "qoheleth"],
    "SNG": ["songofsongs", "sos", "canticles"], "JER": ["jr"], "LAM": ["lm"], "DAN": ["dn"],
    "JOL": ["jl"], "AMO": ["am"], "OBA": ["ob"], "JON": ["jnh"], "MIC": ["mc"], "HAB": ["hb"],
    "ZEP": ["zp"], "HAG": ["hg"], "ZEC": ["zc"], "MAL": ["ml"], "MAT": ["mt"], "MRK": ["mk", "mr"],
    "LUK": ["lk"], "JHN": ["jn"], "ROM": ["rm"], "PHP": ["phil", "pp"], "PHM": ["philem", "phlm"],
    "JAS": ["jm"], "1PE": ["1pt"], "2PE": ["2pt"], "1JN": ["1jhn"], "2JN": ["2jhn"], "3JN": ["3jhn"],
    "REV": ["rv", "revelations"],
}
# Book names as used in a single reference ("Psalm 23:1", not "Psalms 23:1").
DISPLAY_NAMES = {"PSA": "Psalm"}

# "john 3:16", "1 jn 4:8", "ps 119:105-106", "jude 3" (single-chapter book).
REFERENCE_RE = re.compile(
    r"^\s*(?P<book>.*?[a-z].*?)\s*(?P<chapter>\d+)"
    r"(?:\s*[:.]\s*(?P<start>\d+)(?:\s*[-–]\s*(?P<end>\d+))?)?\s*$",
    re.IGNORECASE,
)
_ORDINAL_RE = re.compile(r"^(iii|ii|i|1st|2nd|3rd|first|second|third)\s+")
_ORDINALS = {"i": "1", "ii": "2", "iii": "3", "1st": "1", "2nd": "2", "3rd": "3",
             "first": "1", "second": "2", "third": "3"}


def normalize(name):
    """Reduce a book name to lowercase letters and digits: "I John" -> "1john"."""
    name = _ORDINAL_RE.sub(lambda m: _ORDINALS[m.group(1)], name.strip().lower())
    return re.sub(r"[^a-z0-9]", "", name)


@dataclass(frozen=True)
class Passage:
    reference: str  # e.g. "John 3:16-17"
    verses: list  # [(verse number, text)], skipping any the BSB omits

    @property
    def text(self):
        """The verses as one line, numbering each verse after the first."""
        return " ".join(text if i == 0 else f"{number} {text}"
                        for i, (number, text) in enumerate(self.verses))


class Bible:
    def __init__(self, data):
        self.translation = data["translation"]
        self.books = data["books"]
        self._names = {}  # normalized name or alias -> book
        for book in self.books:
            for name in [book["name"], book["id"], *ALIASES.get(book["id"], [])]:
                self._names[normalize(name)] = book

    @classmethod
    def load(cls, path=DATA_FILE):
        with gzip.open(path, "rb") as f:
            return cls(json.load(f))

    def find_book(self, name):
        """Return the book for a name, abbreviation or unambiguous prefix.

        Raises ValueError for an unknown or ambiguous name.
        """
        key = normalize(name)
        if key in self._names:
            return self._names[key]
        matches = {}
        if len(key) >= 2:
            for alias, book in self._names.items():
                if alias.startswith(key):
                    matches[book["id"]] = book
        if len(matches) == 1:
            return next(iter(matches.values()))
        if matches:
            names = [b["name"] for b in self.books if b["id"] in matches]
            raise ValueError(f"'{name}' could be {', '.join(names)}")
        raise ValueError(f"unknown book '{name}'")

    def lookup(self, reference):
        """Return the Passage for a reference such as "john 3:16" or "ps 23:1-3".

        Raises ValueError, with a message fit to send back, if it can't.
        """
        m = REFERENCE_RE.match(reference)
        if not m:
            raise ValueError("try e.g. john 3:16")
        book = self.find_book(m["book"])
        chapters = book["chapters"]
        name = DISPLAY_NAMES.get(book["id"], book["name"])
        chapter = int(m["chapter"])
        if m["start"] is None:
            if len(chapters) != 1:
                raise ValueError(f"which verse? e.g. {name} {chapter}:1")
            # "jude 3": single-chapter books are cited by verse alone.
            chapter, start = 1, chapter
        else:
            start = int(m["start"])
        end = int(m["end"]) if m["end"] else start
        if not 1 <= chapter <= len(chapters):
            raise ValueError(f"{book['name']} has {len(chapters)} chapters")
        verses = chapters[chapter - 1]
        if not 1 <= start <= len(verses) or not 1 <= end <= len(verses):
            raise ValueError(f"{name} {chapter} has {len(verses)} verses")
        if end < start:
            raise ValueError(f"backwards range {start}-{end}")

        ref = f"{name} {chapter}:{start}" + (f"-{end}" if end != start else "")
        found = [(n, verses[n - 1]) for n in range(start, end + 1) if verses[n - 1]]
        if not found:
            raise ValueError(f"{ref} is not in the {self.translation} text")
        return Passage(ref, found)


@functools.cache
def default_bible():
    """The bundled BSB, loaded on first use."""
    return Bible.load()
