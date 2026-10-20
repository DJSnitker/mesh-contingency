"""Download the Berean Standard Bible and write the compact copy the bot reads.

    python -m mesh_contingency.bible.build [--source complete.simple.json]

The BSB is public domain (dedicated April 30, 2023; see https://berean.bible/),
so it can be bundled and quoted without attribution. The text comes from the
Free Use Bible API (https://bible.helloao.org). Only needs re-running to pick
up corrections to the source text.
"""

import argparse
import gzip
import json
import re
import urllib.request

from . import DATA_FILE

SOURCE_URL = "https://bible.helloao.org/api/BSB/complete.simple.json"
USER_AGENT = "mesh-contingency (bible download)"
TIMEOUT = 120

# Typographic characters in the source, mapped to ASCII so a reply's length in
# characters is also its length in bytes on the mesh.
ASCII = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                       "—": "--", "–": "-", "…": "..."})


def clean(text):
    """Return verse text on one line, in plain ASCII.

    Raises ValueError for any character left that isn't printable ASCII, so a
    change in the source text can't slip through unnoticed.
    """
    # Footnote markers and poetry line breaks leave stray whitespace beside
    # punctuation ("Sivan )", "harm—\nmay"); the BSB closes up em dashes.
    text = re.sub(r"\s*—\s*", "—", text)
    text = re.sub(r"\s+([),.;:!?’”])", r"\1", text)
    text = re.sub(r"\s+", " ", text.translate(ASCII)).strip()
    bad = sorted({c for c in text if not " " <= c <= "~"})
    if bad:
        raise ValueError(f"unexpected characters {bad!r} in: {text}")
    return text


def convert(source):
    """Return the compact form of a helloao complete.simple.json document.

    {"translation": "BSB", "books": [{"id": "GEN", "name": "Genesis",
    "chapters": [["verse 1", "verse 2", ...], ...]}, ...]}

    Verses the BSB omits (e.g. Matthew 17:21, kept only as a footnote) are "".
    """
    books = []
    for book in source["books"]:
        chapters = []
        for chapter in book["chapters"]:
            verses = {item["number"]: clean(item["text"])
                      for item in chapter["chapter"]["content"] if item["type"] == "verse"}
            chapters.append([verses.get(n, "") for n in range(1, max(verses) + 1)])
        books.append({"id": book["id"], "name": book["commonName"], "chapters": chapters})
    return {"translation": source["translation"]["shortName"], "books": books}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", help="local copy of complete.simple.json (downloaded if omitted)")
    args = parser.parse_args()

    if args.source:
        with open(args.source, "rb") as f:
            source = json.load(f)
    else:
        print(f"Downloading {SOURCE_URL}...")
        req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            source = json.load(resp)

    data = convert(source)
    raw = json.dumps(data, separators=(",", ":")).encode()
    # mtime=0 keeps the output identical for identical input.
    with open(DATA_FILE, "wb") as f:
        f.write(gzip.compress(raw, mtime=0))
    verses = sum(len(c) for b in data["books"] for c in b["chapters"])
    print(f"Wrote {DATA_FILE} ({len(data['books'])} books, {verses} verses, "
          f"{DATA_FILE.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
