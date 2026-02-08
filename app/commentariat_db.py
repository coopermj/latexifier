"""Local SQLite access to the commentariat database."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "commentariat.db"

# ---------------------------------------------------------------------------
# Book-name normalisation (ported from commentariat/app/books.py)
# ---------------------------------------------------------------------------

BOOK_ALIASES: Dict[str, List[str]] = {
    "Genesis": ["gen", "ge", "gn"],
    "Exodus": ["exod", "exo", "ex"],
    "Leviticus": ["lev", "lv", "levit"],
    "Numbers": ["num", "nm", "nb"],
    "Deuteronomy": ["deut", "dt", "deu"],
    "Joshua": ["josh", "jos", "jsh"],
    "Judges": ["judg", "jdg", "jdgs", "jgs"],
    "Ruth": ["ruth", "ru", "rth"],
    "1 Samuel": ["1sam", "1samuel", "1sa", "1sm", "isamuel", "firstsamuel"],
    "2 Samuel": ["2sam", "2samuel", "2sa", "2sm", "iisamuel", "secondsamuel"],
    "1 Kings": ["1kgs", "1kings", "1ki", "1k", "ikings", "firstkings"],
    "2 Kings": ["2kgs", "2kings", "2ki", "2k", "iikings", "secondkings"],
    "1 Chronicles": ["1chr", "1chron", "1chronicles", "1ch", "ichronicles", "firstchronicles"],
    "2 Chronicles": ["2chr", "2chron", "2chronicles", "2ch", "iichronicles", "secondchronicles"],
    "Ezra": ["ezra", "ezr"],
    "Nehemiah": ["neh", "ne", "nehemiah"],
    "Esther": ["esth", "est", "es"],
    "Job": ["job", "jb"],
    "Psalms": ["ps", "psa", "psalm", "psalms"],
    "Proverbs": ["prov", "pr", "prv"],
    "Ecclesiastes": ["eccl", "ecc", "ec", "qoh"],
    "Song of Solomon": ["song", "songofsolomon", "songofsongs", "cant", "canticles", "sos"],
    "Isaiah": ["isa", "is", "isaiah"],
    "Jeremiah": ["jer", "je", "jeremiah"],
    "Lamentations": ["lam", "la", "lamentations"],
    "Ezekiel": ["ezek", "eze", "ezk"],
    "Daniel": ["dan", "da", "dn"],
    "Hosea": ["hos", "ho"],
    "Joel": ["joel", "joe", "jl"],
    "Amos": ["amos", "am"],
    "Obadiah": ["obad", "ob", "oba"],
    "Jonah": ["jonah", "jon", "jh"],
    "Micah": ["mic", "mc"],
    "Nahum": ["nah", "na"],
    "Habakkuk": ["hab", "hb"],
    "Zephaniah": ["zeph", "zep", "zp"],
    "Haggai": ["hag", "hg"],
    "Zechariah": ["zech", "zec", "zc"],
    "Malachi": ["mal", "ml"],
    "Matthew": ["matt", "mt", "mat"],
    "Mark": ["mark", "mr", "mk"],
    "Luke": ["luke", "lk", "lu"],
    "John": ["john", "jn", "jhn"],
    "Acts": ["acts", "ac"],
    "Romans": ["rom", "ro", "rm"],
    "1 Corinthians": ["1cor", "1corinthians", "1co", "icor", "firstcorinthians"],
    "2 Corinthians": ["2cor", "2corinthians", "2co", "iicor", "secondcorinthians"],
    "Galatians": ["gal", "ga"],
    "Ephesians": ["eph", "ep"],
    "Philippians": ["phil", "php", "phl"],
    "Colossians": ["col", "co"],
    "1 Thessalonians": ["1thess", "1thessalonians", "1th", "ithess", "firstthessalonians"],
    "2 Thessalonians": ["2thess", "2thessalonians", "2th", "iithess", "secondthessalonians"],
    "1 Timothy": ["1tim", "1timothy", "1ti", "itimothy", "firsttimothy"],
    "2 Timothy": ["2tim", "2timothy", "2ti", "iitimothy", "secondtimothy"],
    "Titus": ["titus", "tit", "ti"],
    "Philemon": ["phlm", "phm", "philemon"],
    "Hebrews": ["heb", "he"],
    "James": ["jas", "jam", "jm"],
    "1 Peter": ["1pet", "1peter", "1pe", "ipeter", "firstpeter"],
    "2 Peter": ["2pet", "2peter", "2pe", "iipeter", "secondpeter"],
    "1 John": ["1john", "1jn", "1jo", "ijohn", "firstjohn"],
    "2 John": ["2john", "2jn", "2jo", "iijohn", "secondjohn"],
    "3 John": ["3john", "3jn", "3jo", "iiijohn", "thirdjohn"],
    "Jude": ["jude", "jud"],
    "Revelation": ["rev", "re", "revelation", "apocalypse"],
}


def _norm(token: str) -> str:
    return "".join(ch for ch in token.lower() if ch.isalnum())


_ALIAS_TO_CANONICAL: Dict[str, str] = {}
for _canonical, _aliases in BOOK_ALIASES.items():
    for _alias in [_canonical, *_aliases]:
        _ALIAS_TO_CANONICAL[_norm(_alias)] = _canonical


def normalize_book(value: str) -> str:
    """Return the canonical book name for *value*, or raise ValueError."""
    if not value:
        raise ValueError("Book name is required")
    canonical = _ALIAS_TO_CANONICAL.get(_norm(value))
    if not canonical:
        raise ValueError(f"Unknown book: {value}")
    return canonical


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def get_commentary(slug: str) -> Optional[Dict[str, object]]:
    """Look up a commentary row by slug (case-insensitive)."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM commentaries WHERE lower(slug) = lower(?)",
            (slug,),
        ).fetchone()
    return dict(row) if row else None


def list_entries_for_chapter(
    commentary_id: int, book: str, chapter: int
) -> List[Dict[str, object]]:
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT verse_start, verse_end, text
            FROM entries
            WHERE commentary_id = ? AND book = ? AND chapter = ?
            ORDER BY verse_start, verse_end
            """,
            (commentary_id, book, chapter),
        ).fetchall()
    return [dict(r) for r in rows]


def list_entries_for_verse(
    commentary_id: int, book: str, chapter: int, verse: int
) -> List[Dict[str, object]]:
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT verse_start, verse_end, text
            FROM entries
            WHERE commentary_id = ?
              AND book = ?
              AND chapter = ?
              AND verse_start <= ?
              AND verse_end >= ?
            ORDER BY verse_start, verse_end
            """,
            (commentary_id, book, chapter, verse, verse),
        ).fetchall()
    return [dict(r) for r in rows]
