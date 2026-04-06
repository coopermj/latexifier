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


def test_preamble_contains_intword():
    """The \intword command must be in the generated preamble."""
    import asyncio
    from app.sermon_latex import generate_sermon_latex
    from app.models import SermonOutline, SermonMetadata

    outline = SermonOutline(
        metadata=SermonMetadata(title="Test", speaker=None, date=None, series=None),
        main_passage="Genesis 1:1",   # OT → no interlinear, but preamble always emitted
        points=[],
    )
    latex = asyncio.get_event_loop().run_until_complete(
        generate_sermon_latex(outline, include_main_passage=False)
    )
    assert r"\newcommand{\intword}" in latex


def test_render_interlinear_passage_structure():
    from app.sermon_latex import _render_interlinear_passage

    words = [
        {"greek": "Ἐν", "lemma": "ἐν", "strongs": "1722", "gloss": "In", "morph": "PREP", "verse": 1},
        {"greek": "ἀρχῇ", "lemma": "ἀρχή", "strongs": "746", "gloss": "beginning", "morph": "N-DSF", "verse": 1},
        {"greek": "ἦν", "lemma": "εἰμί", "strongs": "2258", "gloss": "was", "morph": "V-IAI-3S", "verse": 2},
    ]
    lines = _render_interlinear_passage(words, "John 1:1-2", "ESV")
    combined = "\n".join(lines)

    assert r"\begin{paracol}{2}" in combined
    assert r"\switchcolumn" in combined
    assert r"\hypertarget{interlinear}{}" in combined
    assert r"\intword{Ἐν}{In}{1722}" in combined
    assert r"\intword{ἀρχῇ}{beginning}{746}" in combined
    # Verse boundary markers
    assert r"{\color{gray}\scriptsize 1}" in combined
    assert r"{\color{gray}\scriptsize 2}" in combined
    # ESV placeholder in right column (nolinks=true for paracol)
    assert "[[scripture:John 1:1-2|ESV|nolinks=true]]" in combined
