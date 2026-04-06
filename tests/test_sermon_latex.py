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


def test_render_lexicon_appendix_entry_structure():
    from unittest.mock import patch
    from app.sermon_latex import _render_lexicon_appendix

    sample_lsj = {"3056": {"lemma": "λόγος", "entry": "I. the word. II. reason."}}
    sample_strongs = {"3056": {"greek": "λόγος", "translit": "lógos", "def": "a word, speech"}}

    sample_words = [{"greek": "λόγος", "lemma": "λόγος", "strongs": "3056", "gloss": "word", "morph": "N-NSM", "verse": 1}]
    with patch("app.sermon_latex.STRONGS_GREEK", sample_strongs), \
         patch("app.sermon_latex.get_lsj_entry", side_effect=lambda n: sample_lsj.get(n, {}).get("entry")):
        lines = _render_lexicon_appendix(sample_words)

    combined = "\n".join(lines)
    assert r"\hypertarget{lex-3056}{}" in combined
    assert "λόγος" in combined
    assert "lógos" in combined
    assert "G3056" in combined
    assert "a word, speech" in combined
    assert "I. the word. II. reason." in combined
    assert r"\section{Lexicon}" in combined


def test_render_lexicon_appendix_no_lsj_still_renders():
    from unittest.mock import patch
    from app.sermon_latex import _render_lexicon_appendix

    sample_strongs = {"1722": {"greek": "ἐν", "translit": "en", "def": "in, by, with"}}

    sample_words = [{"greek": "ἐν", "lemma": "ἐν", "strongs": "1722", "gloss": "in", "morph": "PREP", "verse": 1}]
    with patch("app.sermon_latex.STRONGS_GREEK", sample_strongs), \
         patch("app.sermon_latex.get_lsj_entry", return_value=None):
        lines = _render_lexicon_appendix(sample_words)

    combined = "\n".join(lines)
    assert "ἐν" in combined
    assert "in, by, with" in combined
    # No L&S block for words with no LSJ entry
    assert "Liddell" not in combined


def test_render_lexicon_appendix_empty():
    from app.sermon_latex import _render_lexicon_appendix
    lines = _render_lexicon_appendix([])
    assert lines == []


@pytest.mark.asyncio
async def test_generate_sermon_latex_ot_no_interlinear():
    """OT passage → no interlinear hypertarget, no lexicon section."""
    from unittest.mock import patch
    from app.sermon_latex import generate_sermon_latex
    from app.models import SermonOutline, SermonMetadata

    outline = SermonOutline(
        metadata=SermonMetadata(title="Test", speaker=None, date=None, series=None),
        main_passage="Genesis 1:1",
        points=[],
    )
    with patch("app.sermon_latex.fetch_scripture", side_effect=Exception("no network")):
        latex = await generate_sermon_latex(outline, include_main_passage=True)

    assert r"\hypertarget{interlinear}{}" not in latex
    assert r"\section{Lexicon}" not in latex
    # Fallback to multicols
    assert r"\begin{multicols}{2}" in latex


@pytest.mark.asyncio
async def test_generate_sermon_latex_nt_toc_has_interlinear_and_lexicon():
    """NT passage → TOC contains Greek Interlinear and Lexicon links."""
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.sermon_latex import generate_sermon_latex
    from app.models import SermonOutline, SermonMetadata

    outline = SermonOutline(
        metadata=SermonMetadata(title="Test", speaker=None, date=None, series=None),
        main_passage="Ephesians 4:22",
        points=[],
    )
    sample_words = [
        {"greek": "ἀποθέσθαι", "lemma": "ἀποτίθημι", "strongs": "659",
         "gloss": "to put off", "morph": "V-AMN", "verse": 22},
    ]
    with patch("app.sermon_latex.get_passage_words", return_value=sample_words), \
         patch("app.sermon_latex.fetch_scripture", side_effect=Exception("no network")):
        latex = await generate_sermon_latex(outline, include_main_passage=True)

    assert r"\hyperlink{interlinear}{Greek Interlinear}" in latex
    assert r"\hyperlink{lexicon}{Lexicon}" in latex
    assert r"\section{Lexicon}" in latex
    assert r"\hypertarget{interlinear}{}" in latex
    assert r"\begin{multicols}{2}" not in latex   # no fallback multicols for NT
