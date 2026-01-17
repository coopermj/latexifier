"""Commentariat API client for fetching Biblical commentary."""

import logging
import re
from dataclasses import dataclass
from enum import Enum

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://commentariat-production.up.railway.app"


class CommentarySource(str, Enum):
    """Available commentary sources."""
    MHC = "mhc"  # Matthew Henry's Complete Commentary
    CALVIN = "calvincommentaries"  # Calvin's Collected Commentaries


@dataclass
class CommentaryEntry:
    """A single commentary entry for a verse or verse range."""
    verse_start: int
    verse_end: int
    text: str


@dataclass
class CommentaryResult:
    """Result from a commentary lookup."""
    source: CommentarySource
    source_name: str
    book: str
    chapter: int
    verse: int | None
    entries: list[CommentaryEntry]


class CommentaryLookupError(Exception):
    """Raised when commentary lookup fails."""


def _parse_reference(reference: str) -> tuple[str, int, int | None, int | None]:
    """
    Parse a scripture reference into (book, chapter, verse_start, verse_end).

    Examples:
        "John 3:16" -> ("John", 3, 16, 16)
        "Romans 8:1-4" -> ("Romans", 8, 1, 4)
        "1 John 2:3" -> ("1 John", 2, 3, 3)
        "Genesis 1" -> ("Genesis", 1, None, None)
    """
    reference = reference.strip()

    # Pattern for book + chapter:verse-verse or book + chapter:verse or book + chapter
    # Handles numbered books like "1 John", "2 Kings"
    pattern = re.compile(
        r"^(\d?\s*[A-Za-z]+(?:\s+[A-Za-z]+)*)\s+"  # Book name (with optional number prefix)
        r"(\d+)"  # Chapter
        r"(?::(\d+)(?:\s*[-–]\s*(\d+))?)?"  # Optional :verse or :verse-verse
        r"$"
    )

    match = pattern.match(reference)
    if not match:
        raise CommentaryLookupError(f"Could not parse reference: {reference}")

    book = match.group(1).strip()
    chapter = int(match.group(2))
    verse_start = int(match.group(3)) if match.group(3) else None
    verse_end = int(match.group(4)) if match.group(4) else verse_start

    return book, chapter, verse_start, verse_end


def clean_commentary_text(text: str) -> str:
    """Remove SWORD formatting artifacts and leading passage quotes from commentary text."""
    # Replace \par with newlines first
    text = text.replace('\\par', '\n\n')

    # Strip leading passage text - MHC often quotes verses before commentary
    # Pattern: verses are marked with * 1 *, * 2 *, etc. followed by verse text
    # The actual commentary usually starts after multiple spaces or a clear break

    # First, check if text starts with verse markers
    if re.match(r'^\s*\*\s*\d+\s*\*', text):
        # Find where the quoted passage ends and commentary begins
        # Look for a section after verse markers that starts a new thought
        # Usually there's significant whitespace (3+ spaces) between passage and commentary
        parts = re.split(r'\s{3,}', text, maxsplit=1)
        if len(parts) > 1 and len(parts[1]) > 100:
            # Take the commentary part (after the passage quote)
            text = parts[1]

    # Remove any remaining verse markers like * 1 *
    text = re.sub(r'\*\s*\d+\s*\*', '', text)
    # Remove italics markers like * word *
    text = re.sub(r'\*\s*([^*]+?)\s*\*', r'\1', text)

    # Convert multiple spaces (3+) to paragraph breaks BEFORE normalizing
    text = re.sub(r'  +', '\n\n', text)

    # Normalize single spaces and tabs
    text = re.sub(r'[ \t]+', ' ', text)
    # Normalize multiple newlines to double newlines
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    return text.strip()


async def fetch_verse_commentary(
    source: CommentarySource,
    book: str,
    chapter: int,
    verse: int
) -> CommentaryResult | None:
    """
    Fetch commentary for a specific verse.

    Returns None if no commentary available for this verse/source.
    """
    url = f"{BASE_URL}/commentaries/{source.value}/{book}/{chapter}/{verse}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)

            if response.status_code == 404:
                return None

            response.raise_for_status()
            data = response.json()

            entries = [
                CommentaryEntry(
                    verse_start=e["verse_start"],
                    verse_end=e["verse_end"],
                    text=clean_commentary_text(e["text"])
                )
                for e in data.get("entries", [])
            ]

            if not entries:
                return None

            return CommentaryResult(
                source=source,
                source_name=data.get("commentary", {}).get("name", source.value),
                book=data.get("book", book),
                chapter=data.get("chapter", chapter),
                verse=data.get("verse", verse),
                entries=entries
            )
    except httpx.HTTPStatusError as exc:
        logger.warning("Commentary lookup failed for %s %s:%s (%s): %s",
                       book, chapter, verse, source.value, exc)
        return None
    except Exception as exc:
        logger.warning("Commentary lookup error for %s %s:%s (%s): %s",
                       book, chapter, verse, source.value, exc)
        return None


async def fetch_chapter_commentary(
    source: CommentarySource,
    book: str,
    chapter: int
) -> CommentaryResult | None:
    """
    Fetch commentary for an entire chapter.

    Returns None if no commentary available for this chapter/source.
    """
    url = f"{BASE_URL}/commentaries/{source.value}/{book}/{chapter}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)

            if response.status_code == 404:
                return None

            response.raise_for_status()
            data = response.json()

            entries = [
                CommentaryEntry(
                    verse_start=e["verse_start"],
                    verse_end=e["verse_end"],
                    text=clean_commentary_text(e["text"])
                )
                for e in data.get("entries", [])
            ]

            if not entries:
                return None

            return CommentaryResult(
                source=source,
                source_name=data.get("commentary", {}).get("name", source.value),
                book=data.get("book", book),
                chapter=data.get("chapter", chapter),
                verse=None,
                entries=entries
            )
    except httpx.HTTPStatusError as exc:
        logger.warning("Commentary lookup failed for %s %s (%s): %s",
                       book, chapter, source.value, exc)
        return None
    except Exception as exc:
        logger.warning("Commentary lookup error for %s %s (%s): %s",
                       book, chapter, source.value, exc)
        return None


async def fetch_commentary_for_reference(
    reference: str,
    source: CommentarySource = CommentarySource.MHC
) -> CommentaryResult | None:
    """
    Fetch commentary for a scripture reference.

    For verse-specific references (John 3:16), fetches verse commentary.
    For chapter references (Genesis 1), fetches chapter commentary.
    For verse ranges (Romans 8:1-4), fetches the first verse's commentary.
    """
    try:
        book, chapter, verse_start, verse_end = _parse_reference(reference)
    except CommentaryLookupError:
        logger.warning("Could not parse reference for commentary: %s", reference)
        return None

    if verse_start is not None:
        return await fetch_verse_commentary(source, book, chapter, verse_start)
    else:
        return await fetch_chapter_commentary(source, book, chapter)


async def fetch_all_commentaries_for_reference(
    reference: str
) -> dict[CommentarySource, CommentaryResult]:
    """
    Fetch commentary from all available sources for a reference.

    Returns dict mapping source to result (only includes sources that returned data).
    """
    results = {}

    for source in CommentarySource:
        result = await fetch_commentary_for_reference(reference, source)
        if result:
            results[source] = result

    return results
