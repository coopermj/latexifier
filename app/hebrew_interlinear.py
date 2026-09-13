"""Offline Hebrew/Aramaic OT interlinear, using English (NRSV) versification.

See docs/hebrew-data.md for source text choices and lexical attribution.
Word order is logical source order: render Hebrew with an RTL-aware font/layout.
"""
import gzip
import json
import logging
import re
import zlib
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)
_DATA_DIR = Path(__file__).parent / 'data' / 'hebrew'
BOOK_CODES = dict(zip(
    ('Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|'
     '1 Samuel|2 Samuel|1 Kings|2 Kings|1 Chronicles|2 Chronicles|Ezra|'
     'Nehemiah|Esther|Job|Psalms|Proverbs|Ecclesiastes|Song of Solomon|'
     'Isaiah|Jeremiah|Lamentations|Ezekiel|Daniel|Hosea|Joel|Amos|Obadiah|'
     'Jonah|Micah|Nahum|Habakkuk|Zephaniah|Haggai|Zechariah|Malachi').split('|'),
    ('Gen Exo Lev Num Deu Jos Jdg Rut 1Sa 2Sa 1Ki 2Ki 1Ch 2Ch Ezr Neh Est '
     'Job Psa Pro Ecc Sng Isa Jer Lam Ezk Dan Hos Jol Amo Oba Jon Mic Nam '
     'Hab Zep Hag Zec Mal').split(),
))
_ALIASES = {name.lower(): code for name, code in BOOK_CODES.items()}
_ALIASES.update({code.lower(): code for code in BOOK_CODES.values()})
_ALIASES.update({'psalm': 'Psa', 'ps': 'Psa', 'song of songs': 'Sng', 'song': 'Sng',
                 'canticles': 'Sng', 'ezek': 'Ezk', 'joel': 'Jol', 'nah': 'Nam'})
_REF_RE = re.compile(r'^(.+?)\s+(\d+)(?::(\d+)(?:-(?:(\d+):)?(\d+))?)?$')
_STRONG_RE = re.compile(r'^[Hh](\d{1,4})([A-Za-z]*)$')


@lru_cache(maxsize=1)
def _load_manifest() -> dict:
    try:
        return json.loads((_DATA_DIR / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        logger.warning('Hebrew corpus manifest unavailable', exc_info=True)
        return {}


@lru_cache(maxsize=3)
def _load_book(code: str) -> dict:
    """Cache at most three OT books; reject damaged/incomplete corpus files."""
    if code not in BOOK_CODES.values():
        return {}
    try:
        with gzip.open(_DATA_DIR / f'{code}.json.gz', 'rt', encoding='utf-8') as stream:
            data = json.load(stream)
        expected = _load_manifest()['books'][code]['verse_word_counts']
        actual = {ch: {v: len(words) for v, words in verses.items()}
                  for ch, verses in data.items()}
        if actual != expected:
            raise ValueError(f'Incomplete Hebrew corpus for {code}')
        for verses in data.values():
            for words in verses.values():
                if not isinstance(words, list) or not words:
                    raise ValueError('Missing Hebrew tokens')
                for word in words:
                    if (not isinstance(word, list) or len(word) != 5
                            or not all(isinstance(field, str) for field in word)
                            or not word[0] or not _STRONG_RE.fullmatch(word[2])
                            or not word[3].startswith(('H', 'A')) or not word[4]):
                        raise ValueError('Malformed Hebrew token')
        return data
    except (OSError, EOFError, ValueError, KeyError, TypeError, AttributeError, zlib.error):
        logger.warning('Hebrew corpus unavailable for %s', code, exc_info=True)
        return {}


@lru_cache(maxsize=1)
def _load_lexicon() -> dict:
    try:
        with gzip.open(_DATA_DIR / 'lexicon.json.gz', 'rt', encoding='utf-8') as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            raise ValueError('Malformed Hebrew lexicon')
        for entry in data.values():
            if not isinstance(entry, dict) or not all(
                    isinstance(entry.get(key), str)
                    for key in ('hebrew', 'translit', 'gloss', 'def', 'definition_strongs')):
                raise ValueError('Malformed Hebrew lexical entry')
        return data
    except (OSError, EOFError, ValueError, zlib.error):
        logger.warning('Hebrew lexicon unavailable', exc_info=True)
        return {}


def get_hebrew_lexicon_entry(strongs: str) -> dict | None:
    """Return exact STEP dStrong lemma/gloss plus the broad Strong definition.

    Suffix case is meaningful and preserved. Base H-number queries are allowed;
    an unknown extended identifier does not silently select a different sense.
    ``definition_strongs`` names the broad original entry behind ``def``.
    """
    if not isinstance(strongs, str) or not (match := _STRONG_RE.fullmatch(strongs.strip())):
        return None
    identifier = f'H{int(match[1]):04d}{match[2]}'
    entry = _load_lexicon().get(identifier)
    return dict(entry) if entry else None


def get_hebrew_passage_words(reference: str) -> list[dict] | None:
    """Return complete verse/chapter/range words, or None for unavailable data.

    Supports canonical OT names, source abbreviations and common Psalm/Song
    aliases. Chapter queries include Psalm superscriptions (verse zero); verse
    queries follow English numbering. Explicit verse zero requires source data.
    Each token carries hebrew, gloss, strongs, lemma, morph, text_type, chapter,
    verse, and language (hebrew/aramaic). Returned dictionaries are fresh copies.
    """
    if not isinstance(reference, str) or len(reference) > 200:
        return None
    ref = reference.strip().replace('–', '-').replace('—', '-')
    match = _REF_RE.fullmatch(ref)
    if not match:
        return None
    book, c_start, v_start, c_end, v_end = match.groups()
    code = _ALIASES.get(' '.join(book.lower().replace('.', '').split()))
    if code is None:
        return None
    ch_start = int(c_start)
    ch_end = int(c_end) if c_end else ch_start
    if ch_start < 1 or ch_end < ch_start:
        return None
    data = _load_book(code)
    # Bound chapter enumeration before constructing potentially huge ranges.
    if not data or ch_start > len(data) or ch_end > len(data):
        return None
    first_verse = int(v_start) if v_start is not None else None
    last_verse = int(v_end) if v_end is not None else first_verse
    if ch_start == ch_end and first_verse is not None and last_verse < first_verse:
        return None
    selected = []
    for chapter in range(ch_start, ch_end + 1):
        verses = data.get(str(chapter))
        if not verses:
            return None
        first = (first_verse if chapter == ch_start else 1) if first_verse is not None else min(map(int, verses))
        last = last_verse if chapter == ch_end and last_verse is not None else max(map(int, verses))
        if first > last or last > max(map(int, verses)):
            return None
        for verse in range(first, last + 1):
            words = verses.get(str(verse))
            if not words:
                return None
            selected.append((chapter, verse, words))
    result = []
    for chapter, verse, words in selected:
        for hebrew, gloss, strongs, morph, text_type in words:
            entry = get_hebrew_lexicon_entry(strongs)
            if not entry:
                return None
            result.append({'hebrew': hebrew, 'gloss': gloss, 'strongs': strongs,
                           'lemma': entry['hebrew'], 'morph': morph, 'text_type': text_type,
                           'chapter': chapter, 'verse': verse,
                           'language': 'aramaic' if morph.startswith('A') else 'hebrew'})
    return result or None
