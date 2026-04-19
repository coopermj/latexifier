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
# Matches "Book Chapter" (no verse)
_CHAP_RE = re.compile(r'^(.+?)\s+(\d+)$')

_BEREAN_PATH = Path(__file__).parent.parent / "data" / "berean_nt.json"


@lru_cache(maxsize=1)
def _load_berean() -> dict:
    if not _BEREAN_PATH.exists():
        return {}
    return json.loads(_BEREAN_PATH.read_text(encoding="utf-8"))


def _parse_ref(reference: str) -> tuple[str, str, int | None, int | None] | None:
    """Return (book, chapter_str, v_start, v_end) or None if unparseable."""
    ref = reference.strip()
    m = _REF_RE.match(ref)
    if m:
        return m.group(1), m.group(2), int(m.group(3)), int(m.group(4)) if m.group(4) else int(m.group(3))
    m = _CHAP_RE.match(ref)
    if m:
        return m.group(1), m.group(2), None, None
    return None


def is_nt_passage(reference: str) -> bool:
    """Return True if the reference names a New Testament book."""
    parsed = _parse_ref(reference)
    return parsed is not None and parsed[0] in _NT_BOOKS


def get_passage_words(reference: str) -> list[dict] | None:
    """
    Return word list for a NT reference, or None for OT/unknown/missing data.

    Each dict has keys: greek, lemma, strongs, gloss, morph, verse (int).
    Accepts both verse-level ("Titus 2:11-15") and chapter-level ("Titus 3").
    """
    parsed = _parse_ref(reference)
    if parsed is None:
        return None
    book, chapter, v_start, v_end = parsed
    if book not in _NT_BOOKS:
        return None

    data = _load_berean()
    ch_data = data.get(book, {}).get(chapter, {})
    if not ch_data:
        return None

    words: list[dict] = []
    if v_start is None:
        # Chapter-level: return all verses in order
        for v in sorted(ch_data.keys(), key=int):
            for w in ch_data[v]:
                words.append({**w, "verse": int(v)})
    else:
        if v_end < v_start:
            logger.warning("get_passage_words: inverted verse range in %r", reference)
            return None
        for v in range(v_start, v_end + 1):
            for w in ch_data.get(str(v), []):
                words.append({**w, "verse": v})

    return words if words else None
