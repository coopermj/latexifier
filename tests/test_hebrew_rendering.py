"""Hebrew must be selected automatically and retain mixed-direction layout."""
import re
import shutil

import pytest

from app.models import SermonMetadata, SermonOutline
from app.sermon_latex import generate_sermon_latex


def test_cross_chapter_markers_and_english_escaping():
    from app.hebrew_rendering import render_hebrew_interlinear
    words = [dict(hebrew='דָּבָר', gloss='word & speech', strongs='H1697', chapter=1, verse=1),
             dict(hebrew='דָּבָר', gloss='word', strongs='H1697', chapter=2, verse=1)]
    tex = '\n'.join(render_hebrew_interlinear(words, 'Isaiah 1:1-2:1', 'NET'))
    assert r'\begin{hebrewverse}{1:1}' in tex
    assert r'\begin{hebrewverse}{2:1}' in tex
    assert r'word \& speech' in tex
    assert '[[scripture:Isaiah 1:1-2:1|NET|nolinks=true]]' in tex


def test_lexicon_deduplicates_extended_hebrew_identifiers(monkeypatch):
    from app import hebrew_rendering
    monkeypatch.setattr(hebrew_rendering, 'get_hebrew_lexicon_entry', lambda _: {
        'hebrew': 'דָּבָר', 'translit': 'davar', 'def': 'word & speech (דבר).',
    })
    word = dict(hebrew='דָּבָר', gloss='word', strongs='H1697A')
    tex = '\n'.join(hebrew_rendering.render_hebrew_lexicon([word, word]))
    assert tex.count(r'\hypertarget{lex-H1697A}') == 1
    assert r'\hebrewtext{דבר}' in tex
    assert r'word \& speech' in tex


@pytest.mark.asyncio
async def test_aramaic_passage_is_labeled_accurately():
    outline = SermonOutline(metadata=SermonMetadata(title="Daniel"),
                            main_passage="Daniel 2:5", points=[])
    tex = await generate_sermon_latex(outline)
    assert r"\hyperlink{interlinear}{Aramaic Interlinear}" in tex


@pytest.mark.asyncio
async def test_ot_main_passage_selects_hebrew_interlinear():
    outline = SermonOutline(metadata=SermonMetadata(title="Creation"),
                            main_passage="Genesis 1:1", points=[])
    tex = await generate_sermon_latex(outline)
    assert r"\hyperlink{interlinear}{Hebrew Interlinear}" in tex
    assert r"\section{Hebrew Lexicon}" in tex
    assert r"\hebrewintword" in tex
    assert "[[scripture:Genesis 1:1|ESV|nolinks=true]]" in tex


@pytest.mark.asyncio
async def test_disabling_main_passage_omits_hebrew_and_lexicon():
    outline = SermonOutline(metadata=SermonMetadata(title="Creation"),
                            main_passage="Genesis 1:1", points=[])
    tex = await generate_sermon_latex(outline, include_main_passage=False)
    assert r"\hypertarget{interlinear}" not in tex
    assert r"\hypertarget{lexicon}" not in tex


@pytest.mark.skipif(not shutil.which("lualatex"), reason="LuaLaTeX is required")
@pytest.mark.asyncio
@pytest.mark.parametrize('reference', ['Genesis 1:1', 'Isaiah 1:26', 'Daniel 2:4'])
async def test_hebrew_words_read_right_to_left_with_ltr_glosses_and_working_links(monkeypatch, reference):
    import pymupdf
    from app.hebrew_interlinear import get_hebrew_passage_words
    from app.routes.web import _compile_without_image

    outline = SermonOutline(metadata=SermonMetadata(title="Creation"),
                            main_passage=reference, points=[])
    tex = await generate_sermon_latex(outline)
    async def replace_scripture(work_dir, main_file):
        path = work_dir / main_file
        path.write_text(re.sub(r'\[\[scripture:[^\]]+\]\]',
                               lambda _: 'English passage reads left to right.', path.read_text()))
    monkeypatch.setattr('app.placeholders.process_scripture_placeholders', replace_scripture)
    from app.compiler import CompilationError
    try:
        pdf, log, _ = await _compile_without_image(tex)
    except CompilationError as error:
        pytest.fail(error.log[-6000:])
    assert 'Missing character' not in log
    assert 'Overfull' not in log
    with pymupdf.open(stream=pdf, filetype='pdf') as doc:
        page = next(page for page in doc if page.search_for('English passage'))
        if reference == 'Genesis 1:1':
            # The corpus' first three Hebrew words have these English glosses.
            beginning, created, god = [page.search_for(word)[0] for word in ('beginning', 'created', 'God')]
            assert beginning.x0 > created.x0 > god.x0
            assert abs(beginning.y0 - god.y0) < 3
            assert page.search_for('English passage')[0].x0 > beginning.x0
        # PyMuPDF may expose named internal destinations as LINK_NAMED.
        links = [link for link in page.get_links() if link.get('nameddest', '').startswith('lex-H')]
        assert len(links) == len(get_hebrew_passage_words(reference))
        for link in links:
            assert link['page'] > page.number
            assert link['nameddest'][4:] in doc[link['page']].get_text()
        assert any('Ezra' in font[3] for font in page.get_fonts())
