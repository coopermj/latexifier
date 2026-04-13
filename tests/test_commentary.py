from unittest.mock import patch

import pytest

from app.commentary import CommentarySource, fetch_chapter_commentary


@pytest.mark.asyncio
async def test_fetch_chapter_commentary_merges_adjacent_duplicate_entries():
    rows = [
        {"verse_start": 1, "verse_end": 1, "text": "Same commentary"},
        {"verse_start": 2, "verse_end": 2, "text": "Same commentary"},
        {"verse_start": 3, "verse_end": 3, "text": "Different commentary"},
    ]

    with (
        patch("app.commentary.commentariat_db.get_commentary", return_value={"id": 1, "name": "Matthew Henry"}),
        patch("app.commentary.commentariat_db.normalize_book", return_value="Psalms"),
        patch("app.commentary.commentariat_db.list_entries_for_chapter", return_value=rows),
    ):
        result = await fetch_chapter_commentary(CommentarySource.MHC, "Psalm", 119)

    assert result is not None
    assert [(entry.verse_start, entry.verse_end, entry.text) for entry in result.entries] == [
        (1, 2, "Same commentary"),
        (3, 3, "Different commentary"),
    ]
