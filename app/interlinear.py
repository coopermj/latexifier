"""Berean Interlinear Bible data access — NT only."""
import json
import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_NT_BOOKS = {
    "Matthew", "Mark", "Luke", "John", "Acts", "Romans",
    "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
    "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews",
    "James", "1 Peter", "2 Peter", "1 John", "2 John", "3 John",
    "Jude", "Revelation",
}

# Matches "Book Chapter:Verse" or "Book Chapter:Verse-Verse"
_REF_RE = re.compile(r'^(.+?)\s+(\d+):(\d+)(?:-(\d+))?$')

_BEREAN_PATH = Path(__file__).parent.parent / "data" / "berean_nt.json"


@lru_cache(maxsize=1)
def _load_berean() -> dict:
    if not _BEREAN_PATH.exists():
        return {}
    return json.loads(_BEREAN_PATH.read_text(encoding="utf-8"))


def is_nt_passage(reference: str) -> bool:
    """Return True if the reference names a New Testament book."""
    m = _REF_RE.match(reference.strip())
    if not m:
        return False
    return m.group(1) in _NT_BOOKS


def get_passage_words(reference: str) -> list[dict] | None:
    """
    Return word list for a NT reference, or None for OT/unknown/missing data.

    Each dict has keys: greek, lemma, strongs, gloss, morph, verse (int).
    """
    m = _REF_RE.match(reference.strip())
    if not m:
        return None
    book = m.group(1)
    if book not in _NT_BOOKS:
        return None
    chapter = m.group(2)
    v_start = int(m.group(3))
    v_end = int(m.group(4)) if m.group(4) else v_start
    if v_end < v_start:
        logger.warning("get_passage_words: inverted verse range in %r", reference)
        return None

    data = _load_berean()
    ch_data = data.get(book, {}).get(chapter, {})
    if not ch_data:
        return None

    words: list[dict] = []
    for v in range(v_start, v_end + 1):
        for w in ch_data.get(str(v), []):
            words.append({**w, "verse": v})

    return words if words else None
