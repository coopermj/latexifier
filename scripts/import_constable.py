"""Import Constable's Expository Notes from StudyLight into commentariat.db.

Usage:
    python scripts/import_constable.py            # all books
    python scripts/import_constable.py Titus      # single book
    python scripts/import_constable.py NT         # New Testament only
    python scripts/import_constable.py OT         # Old Testament only
"""

import re
import sqlite3
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import httpx

DB_PATH = Path(__file__).parent.parent / "data" / "commentariat.db"
BASE_URL = "https://www.studylight.org/commentaries/eng/dcc/{slug}-{chapter}.html"
SLUG_NAME = "constable"
DISPLAY_NAME = "Constable's Expository Notes"
DELAY = 1.2  # seconds between requests

# (canonical DB name, URL slug, chapter count)
BOOKS = [
    ("Genesis",          "genesis",           50),
    ("Exodus",           "exodus",            40),
    ("Leviticus",        "leviticus",         27),
    ("Numbers",          "numbers",           36),
    ("Deuteronomy",      "deuteronomy",       34),
    ("Joshua",           "joshua",            24),
    ("Judges",           "judges",            21),
    ("Ruth",             "ruth",               4),
    ("1 Samuel",         "1-samuel",          31),
    ("2 Samuel",         "2-samuel",          24),
    ("1 Kings",          "1-kings",           22),
    ("2 Kings",          "2-kings",           25),
    ("1 Chronicles",     "1-chronicles",      29),
    ("2 Chronicles",     "2-chronicles",      36),
    ("Ezra",             "ezra",              10),
    ("Nehemiah",         "nehemiah",          13),
    ("Esther",           "esther",            10),
    ("Job",              "job",               42),
    ("Psalms",           "psalms",           150),
    ("Proverbs",         "proverbs",          31),
    ("Ecclesiastes",     "ecclesiastes",      12),
    ("Song of Solomon",  "song-of-solomon",    8),
    ("Isaiah",           "isaiah",            66),
    ("Jeremiah",         "jeremiah",          52),
    ("Lamentations",     "lamentations",       5),
    ("Ezekiel",          "ezekiel",           48),
    ("Daniel",           "daniel",            12),
    ("Hosea",            "hosea",             14),
    ("Joel",             "joel",               3),
    ("Amos",             "amos",               9),
    ("Obadiah",          "obadiah",            1),
    ("Jonah",            "jonah",              4),
    ("Micah",            "micah",              7),
    ("Nahum",            "nahum",              3),
    ("Habakkuk",         "habakkuk",           3),
    ("Zephaniah",        "zephaniah",          3),
    ("Haggai",           "haggai",             2),
    ("Zechariah",        "zechariah",         14),
    ("Malachi",          "malachi",            4),
    ("Matthew",          "matthew",           28),
    ("Mark",             "mark",              16),
    ("Luke",             "luke",              24),
    ("John",             "john",              21),
    ("Acts",             "acts",              28),
    ("Romans",           "romans",            16),
    ("1 Corinthians",    "1-corinthians",     16),
    ("2 Corinthians",    "2-corinthians",     13),
    ("Galatians",        "galatians",          6),
    ("Ephesians",        "ephesians",          6),
    ("Philippians",      "philippians",        4),
    ("Colossians",       "colossians",         4),
    ("1 Thessalonians",  "1-thessalonians",    5),
    ("2 Thessalonians",  "2-thessalonians",    3),
    ("1 Timothy",        "1-timothy",          6),
    ("2 Timothy",        "2-timothy",          4),
    ("Titus",            "titus",              3),
    ("Philemon",         "philemon",           1),
    ("Hebrews",          "hebrews",           13),
    ("James",            "james",              5),
    ("1 Peter",          "1-peter",            5),
    ("2 Peter",          "2-peter",            3),
    ("1 John",           "1-john",             5),
    ("2 John",           "2-john",             1),
    ("3 John",           "3-john",             1),
    ("Jude",             "jude",               1),
    ("Revelation",       "revelation",        22),
]

OT_BOOKS = {b[0] for b in BOOKS[:39]}
NT_BOOKS  = {b[0] for b in BOOKS[39:]}

_VERSE_RE = re.compile(r'[Vv]erses?\s+(\d+)(?:\s*[-–]\s*(\d+))?')


class _SectionParser(HTMLParser):
    """Extract (verse_start, verse_end, text) sections from StudyLight HTML."""

    def __init__(self):
        super().__init__()
        self.sections: list[tuple[int, int, str]] = []
        self._in_h3 = False
        self._in_p = False
        self._cur_verse: tuple[int, int] | None = None
        self._cur_text: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "h3":
            self._flush()
            self._in_h3 = True
            self._cur_text = []
        elif tag == "p" and self._cur_verse:
            self._in_p = True
            self._cur_text.append(" ")

    def handle_endtag(self, tag):
        if tag == "h3":
            self._in_h3 = False
            heading = "".join(self._cur_text).strip()
            m = _VERSE_RE.search(heading)
            if m:
                v1 = int(m.group(1))
                v2 = int(m.group(2)) if m.group(2) else v1
                self._cur_verse = (v1, v2)
                self._cur_text = []
            else:
                self._cur_verse = None
                self._cur_text = []
        elif tag == "p":
            self._in_p = False

    def handle_data(self, data):
        if self._in_h3 or (self._in_p and self._cur_verse):
            self._cur_text.append(data)

    def _flush(self):
        if self._cur_verse and self._cur_text:
            text = " ".join("".join(self._cur_text).split()).strip()
            if text:
                self.sections.append((*self._cur_verse, text))
        self._cur_verse = None
        self._cur_text = []

    def close(self):
        self._flush()
        super().close()


def _fetch_chapter(slug: str, chapter: int) -> list[tuple[int, int, str]]:
    url = BASE_URL.format(slug=slug, chapter=chapter)
    try:
        resp = httpx.get(url, timeout=20, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        parser = _SectionParser()
        parser.feed(resp.text)
        parser.close()
        return parser.sections
    except Exception as e:
        print(f"  ERROR fetching {url}: {e}")
        return []


def _ensure_commentary(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM commentaries WHERE slug = ?", (SLUG_NAME,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO commentaries (slug, name, description, source, language) VALUES (?,?,?,?,?)",
        (SLUG_NAME, DISPLAY_NAME,
         "Verse-by-verse expository notes by Dr. Thomas L. Constable",
         "https://www.studylight.org/commentaries/eng/dcc/",
         "English"),
    )
    conn.commit()
    print(f"Created commentary '{DISPLAY_NAME}' (id={cur.lastrowid})")
    return cur.lastrowid


def import_book(conn: sqlite3.Connection, commentary_id: int, book: str, slug: str, chapters: int):
    print(f"  {book} ({chapters} chapters)...")
    conn.execute("DELETE FROM entries WHERE commentary_id = ? AND book = ?", (commentary_id, book))
    total = 0
    for ch in range(1, chapters + 1):
        sections = _fetch_chapter(slug, ch)
        for v_start, v_end, text in sections:
            conn.execute(
                "INSERT INTO entries (commentary_id, book, chapter, verse_start, verse_end, text) VALUES (?,?,?,?,?,?)",
                (commentary_id, book, ch, v_start, v_end, text),
            )
            total += 1
        if sections:
            conn.commit()
        time.sleep(DELAY)
    print(f"    → {total} entries")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"

    if arg == "NT":
        target = [b for b in BOOKS if b[0] in NT_BOOKS]
    elif arg == "OT":
        target = [b for b in BOOKS if b[0] in OT_BOOKS]
    elif arg == "all":
        target = BOOKS
    else:
        target = [b for b in BOOKS if b[0].lower() == arg.lower()]
        if not target:
            print(f"Unknown book: {arg}")
            sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    commentary_id = _ensure_commentary(conn)
    print(f"Importing {len(target)} book(s) into '{DISPLAY_NAME}'...")

    for book, slug, chapters in target:
        import_book(conn, commentary_id, book, slug, chapters)

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
