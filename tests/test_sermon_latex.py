import pytest
from app.commentary import CommentaryResult, CommentarySource, CommentaryEntry
from app.sermon_latex import _render_commentary_appendix


@pytest.mark.asyncio
async def test_render_commentary_appendix_uses_preloaded():
    """When preloaded results are passed, they are rendered without fetching DB."""
    entry = CommentaryEntry(verse_start=1, verse_end=3, text="Test commentary text.")
    result = CommentaryResult(
        source=CommentarySource.MHC,
        source_name="Matthew Henry",
        book="James", chapter=3, verse=1,
        entries=[entry],
    )
    lines = await _render_commentary_appendix(
        main_passage="James 3:1",
        commentary_sources=[],
        preloaded=[result],
    )
    combined = "\n".join(lines)
    assert "Matthew Henry" in combined
    assert "Test commentary text." in combined


@pytest.mark.asyncio
async def test_render_commentary_appendix_empty_when_no_sources_and_no_preloaded():
    lines = await _render_commentary_appendix(
        main_passage="James 3:1",
        commentary_sources=[],
        preloaded=None,
    )
    assert lines == []
