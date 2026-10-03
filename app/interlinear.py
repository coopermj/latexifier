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

# Matches "Book Chapter:Verse" or "Book Chapter:Verse-Verse" (single chapter)
_REF_RE = re.compile(r'^(.+?)\s+(\d+):(\d+)(?:-(\d+))?$')
# Matches "Book Chapter:Verse-Chapter:Verse" (cross-chapter range)
_MULTI_CHAP_RE = re.compile(r'^(.+?)\s+(\d+):(\d+)-(\d+):(\d+)$')
# Matches "Book Chapter" (no verse)
_CHAP_RE = re.compile(r'^(.+?)\s+(\d+)$')
# Matches "Book Chapter-Chapter" (whole-chapter range, e.g. "Romans 1-2")
_CHAP_RANGE_RE = re.compile(r'^(.+?)\s+(\d+)-(\d+)$')
# Verse number meaning "through the end of the chapter" for whole-chapter ranges
_CHAPTER_END = 999


def _normalize(reference: str) -> str:
    return reference.replace("\u2013", "-").replace("\u2014", "-").strip()

_BEREAN_PATH = Path(__file__).parent.parent / "data" / "berean_nt.json"


@lru_cache(maxsize=1)
def _load_berean() -> dict:
    if not _BEREAN_PATH.exists():
        return {}
    return json.loads(_BEREAN_PATH.read_text(encoding="utf-8"))


def _parse_ref(reference: str) -> tuple[str, str, int | None, int | None] | None:
    """Return (book, chapter_str, v_start, v_end) or None if unparseable. Single-chapter only."""
    ref = _normalize(reference)
    # Skip cross-chapter refs — handled separately
    if _MULTI_CHAP_RE.match(ref) or _CHAP_RANGE_RE.match(ref):
        return None
    m = _REF_RE.match(ref)
    if m:
        return m.group(1), m.group(2), int(m.group(3)), int(m.group(4)) if m.group(4) else int(m.group(3))
    m = _CHAP_RE.match(ref)
    if m:
        return m.group(1), m.group(2), None, None
    return None


def _parse_multi_chap_ref(reference: str) -> tuple[str, int, int, int, int] | None:
    """Return (book, ch_start, v_start, ch_end, v_end) for cross-chapter refs, or None.

    A whole-chapter range ("Romans 1-2") runs from verse 1 to _CHAPTER_END.
    """
    ref = _normalize(reference)
    m = _MULTI_CHAP_RE.match(ref)
    if m:
        return m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))
    m = _CHAP_RANGE_RE.match(ref)
    if m:
        return m.group(1), int(m.group(2)), 1, int(m.group(3)), _CHAPTER_END
    return None


def is_nt_passage(reference: str) -> bool:
    """Return True if the reference names a New Testament book."""
    multi = _parse_multi_chap_ref(reference)
    if multi:
        return multi[0] in _NT_BOOKS
    parsed = _parse_ref(reference)
    return parsed is not None and parsed[0] in _NT_BOOKS


def get_passage_words(reference: str) -> list[dict] | None:
    """
    Return word list for a NT reference, or None for OT/unknown/missing data.

    Each dict has keys: greek, lemma, strongs, gloss, morph, verse (int).
    Accepts verse-level ("Titus 2:11-15"), chapter-level ("Titus 3"),
    cross-chapter ranges ("Acts 15:36-16:5"), and whole-chapter ranges
    ("Romans 1-2").
    """
    data = _load_berean()

    # Cross-chapter range (e.g. "Acts 15:36-16:5")
    multi = _parse_multi_chap_ref(reference)
    if multi:
        book, ch_start, v_start, ch_end, v_end = multi
        if book not in _NT_BOOKS:
            return None
        book_data = data.get(book, {})
        if ch_end < ch_start:
            logger.warning("get_passage_words: inverted chapter range in %r", reference)
            return None
        words: list[dict] = []
        for ch in range(ch_start, ch_end + 1):
            ch_data = book_data.get(str(ch), {})
            if not ch_data:
                return None  # chapter missing: don't return a partial passage
            start_v = v_start if ch == ch_start else 1
            end_v = v_end if ch == ch_end else max(int(k) for k in ch_data) if ch_data else 0
            for v in range(start_v, end_v + 1):
                for w in ch_data.get(str(v), []):
                    words.append({**w, "verse": v})
        return words if words else None

    # Single-chapter or chapter-level ref
    parsed = _parse_ref(reference)
    if parsed is None:
        return None
    book, chapter, v_start, v_end = parsed
    if book not in _NT_BOOKS:
        return None

    ch_data = data.get(book, {}).get(chapter, {})
    if not ch_data:
        return None

    words = []
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
