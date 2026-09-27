import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.placeholders import _format_scripture_body, _render_scripture
from app.scripture import ScriptureVersion


@pytest.mark.parametrize("source", [
    "[2] And God said.",
    "2 And God said.",
    "<b>1:2</b> And God said.",
    '<span class="vref"><b><span class="verseNumber">2</span></b></span> And God said.',
])
def test_verse_gap_is_controlled_by_scripture_package(source):
    formatted = _format_scripture_body("Genesis 1:2", source, True, False)
    assert r"\vs{2}And God said." in formatted


def test_final_render_removes_ai_added_verse_spaces_without_joining_paragraphs():
    rendered = _render_scripture(
        "Genesis 1:2-3", ScriptureVersion.ESV,
        "\\vs{2}  And God said.\n\n\\vs{3}\nAnd it was so.",
    )
    assert "\\vs{2}And God said.\n\n\\vs{3}And it was so." in rendered


def test_net_paragraphs_and_heading_before_chapter_survive_formatting():
    source = '<h3>The Beginning</h3><p><b>1:1</b>In the beginning.</p><p><b>2</b>The earth.</p>'
    formatted = _format_scripture_body("Genesis 1:1-2", source, True, False)
    assert formatted.startswith("\\heading{The Beginning}\n\\ch{1}\n")
    assert "beginning.\n\n\\vs{2}The earth." in formatted
    assert not re.search(r"\\vs\{\d+\}[ \t\n]", formatted)


def test_net_continuation_paragraph_is_not_promoted_to_heading():
    source = '<p><b>1:1</b>In the beginning.</p><p>And the evening and the morning were the first day.</p><p><b>2</b>The earth.</p>'
    formatted = _format_scripture_body("Genesis 1:1-2", source, True, False)
    assert r"\heading" not in formatted
    assert "\n\nAnd the evening and the morning were the first day.\n\n" in formatted


@pytest.mark.parametrize("entrypoint", ["api", "web", "web_image"])
async def test_compilers_use_bundled_typography_ahead_of_stale_storage(tmp_path, monkeypatch, entrypoint):
    from app import compiler
    from app.routes import web
    from app.models import CompileRequest

    styles = tmp_path / "styles"
    styles.mkdir()
    (styles / "scripture.sty").write_text("stale package")
    settings = SimpleNamespace(storage_path=str(tmp_path))
    monkeypatch.setattr(compiler, "get_settings", lambda: settings)
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    seen = []

    async def fake_exec(*args, cwd, **kwargs):
        cwd = Path(cwd)
        assert r"\ProvidesExplPackage{scripture}{2026-08-23}{2.5}" in (cwd / "scripture.sty").read_text()
        assert (cwd / "latexgen-scripture.sty").is_file()
        assert (cwd / "EBGaramond-Regular.otf").is_file()
        assert (cwd / "latexgen-hebrew.sty").is_file()
        assert (cwd / "SILEOT.ttf").is_file()
        seen.append(cwd)
        (cwd / Path(args[-1]).with_suffix(".pdf")).write_bytes(b"%PDF-test")
        return SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b"ok", None)))

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    tex = r"\documentclass{article}\begin{document}Test\end{document}"
    if entrypoint == "api":
        await compiler.compile_latex(CompileRequest(content=tex))
    elif entrypoint == "web":
        await web._compile_without_image(tex)
    else:
        await web._compile_with_image(tex, "cover.png", b"image")
    assert len(seen) == 2
    assert all(not cwd.exists() for cwd in seen)


def test_ai_poetry_wrapping_keeps_native_headings_outside_poetry():
    body = "\\begin{poetry}\n\\vs{1}First line.\n\\heading{A {new} section}\n\\vs{2}Second line.\n\\end{poetry}"
    rendered = _render_scripture("Psalm 1:1-2", ScriptureVersion.ESV, body)
    assert "\\end{poetry}\n\\heading{A {new} section}\n\\begin{poetry}" in rendered
    assert rendered.count(r"\begin{poetry}") == 2


def test_drop_chapter_moves_inside_opening_poetry():
    body = "\\heading{A Psalm}\n\\ch{23}\n\\begin{poetry}\n\\vs{1}The Lord is my shepherd.\n\\end{poetry}"
    rendered = _render_scripture("Psalm 23:1", ScriptureVersion.ESV, body)
    assert "\\heading{A Psalm}\n\\begin{poetry}\n\\ch{23}\\vs{1}" in rendered


@pytest.mark.parametrize("heading", ["Title", "A {new} section", "A multiline\nheading"])
def test_poetry_repair_preserves_commands_after_balanced_heading(heading):
    body = r"\begin{poetry}\vs{1}Before.\heading{" + heading + r"}\vs{2}After.\end{poetry}"
    rendered = _render_scripture("Psalm 1:1-2", ScriptureVersion.ESV, body)
    assert "\\heading{" + heading + "}\n\\begin{poetry}\n\\vs{2}After." in rendered


@pytest.mark.skipif(not shutil.which("lualatex"), reason="LuaLaTeX is required for rendered integration checks")
@pytest.mark.parametrize("entrypoint", ["api", "web", "web_image"])
async def test_real_lualatex_typography_in_all_compilation_paths(entrypoint):
    from app.compiler import compile_latex
    from app.routes.web import _compile_without_image, _compile_with_image
    from app.models import CompileRequest, TexEngine
    import base64

    tex = (Path(__file__).parent / "fixtures" / "scripture_typography.tex").read_text()
    imported = _format_scripture_body(
        "Isaiah 1:1-3",
        '<p class="bodytext"><b>1:1</b>The vision of Isaiah.</p>'
        '<h3>Listen</h3><p class="poetry"><b>2</b>Listen, O heavens,'
        '<p class="poetry">pay attention, O earth!</p>'
        '<h3>After poetry</h3><p class="bodytext"><b>3</b>Prose continues.</p>',
        True, False,
    )
    tex = tex.replace(r"\end{document}", "\\newpage\n" + _render_scripture("Isaiah 1:1-3", ScriptureVersion.NET, imported) + r"\end{document}")
    if entrypoint == "api":
        pdf, log = await compile_latex(CompileRequest(content=tex, engine=TexEngine.LUALATEX))
    elif entrypoint == "web":
        pdf, log, processed = await _compile_without_image(tex)
        assert processed == tex
    else:
        tex = tex.replace(r"\end{document}", r"\includegraphics[width=1mm]{cover.png}\end{document}")
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNoaGgAAAMEAYFL09IQAAAAAElFTkSuQmCC")
        pdf, log, processed = await _compile_with_image(tex, "cover.png", png)
        assert processed == tex
    assert pdf.startswith(b"%PDF-")
    assert re.search(r"scripture\.sty\s+2026-08-23 v2\.5", log)
    assert "EBGaramond-Regular.otf" in log
    assert "JosefinSans-Regular.otf" in log
    assert "JosefinSans-Bold.otf" in log
    assert "JosefinSans-Italic.otf" in log
    assert "JosefinSans-BoldItalic.otf" in log
    assert "Overfull" not in log
    assert "Missing character" not in log


def test_net_implicitly_closed_poetry_paragraphs_keep_word_boundaries():
    source = '<p class="poetry"><b>1:2</b>Listen, O heavens,<p class="poetry">pay attention, O earth!</p><p class="poetry"><b>3</b>An ox knows<p class="poetry">its owner.</p>'
    formatted = _format_scripture_body('Isaiah 1:2-3', source, True, False)
    assert 'heavens,\npay attention' in formatted
    assert 'knows\nits owner.' in formatted
    assert '\\vs{3}An ox' in formatted


def test_html_line_breaks_keep_word_boundaries():
    formatted = _format_scripture_body('Isaiah 1:2', '<p><b>1:2</b>Listen,<br />O heavens,<BR>pay attention.</p>', True, False)
    assert 'Listen,\nO heavens,\npay attention.' in formatted


def test_net_poetry_wrappers_do_not_make_each_verse_a_paragraph():
    source = ('<p class="poetry"><b>1:2</b>Listen, O heavens,'
              '<p class="poetry">pay attention, O earth!</p> '
              '<p class="poetry"><b>3</b>An ox recognizes its owner,</p> '
              '<p class="poetry">but Israel does not recognize me.</p>')
    formatted = _format_scripture_body('Isaiah 1:2-3', source, True, False)
    assert not re.search(r'\n\s*\n', formatted)
    assert 'earth! \n\\vs{3}An ox' in formatted
    assert 'owner, \nbut Israel' in formatted


def test_source_poetry_uses_native_environment_with_prose_and_headings_outside():
    source = ('<p class="bodytext"><b>1:1</b>The vision of Isaiah.</p>'
              '<h3>A prophetic {heading}</h3>'
              '<p class="poetry"><b>2</b>Listen, O heavens,'
              '<p class="poetry">pay attention, O earth!</p>'
              '<h3>A second heading</h3><p class="poetry"><b>3</b>An ox knows its owner.</p>'
              '<p class="bodytext"><b>4</b>Prose continues.</p>')
    text = _format_scripture_body('Isaiah 1:1-4', source, True, False)
    assert text.count(r'\begin{poetry}') == text.count(r'\end{poetry}') == 2
    assert text.index('vision of Isaiah') < text.index(r'\begin{poetry}')
    assert text.rindex(r'\end{poetry}') < text.index('Prose continues')
    for block in re.findall(r'\\begin\{poetry\}(.*?)\\end\{poetry\}', text, re.S):
        assert r'\heading' not in block
    assert 'heavens,\npay attention' in text


@pytest.mark.asyncio
@pytest.mark.parametrize('reply', [
    r'\vs{2}Listen to the Lord.',
    r'\begin{poetry}\vs{2}Listen to Lord.\end{poetry}',
    r'\begin{poetry}\begin{poetry}\vs{2}Listen to the Lord.\end{poetry}\end{poetry}',
])
async def test_ai_cannot_discard_or_corrupt_source_poetry(monkeypatch, reply):
    from app import placeholders
    from unittest.mock import MagicMock
    original = '\\begin{poetry}\n\\vs{2}Listen to the Lord.\n\\end{poetry}'
    response = MagicMock()
    response.json.return_value = {'content': [{'type': 'text', 'text': reply}]}
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = response
    monkeypatch.setattr(placeholders, 'get_settings', lambda: SimpleNamespace(anthropic_api_key='test-only'))
    monkeypatch.setattr(placeholders.httpx, 'AsyncClient', lambda: client)
    assert await placeholders._analyze_scripture_with_ai(original, 'Isaiah 1:2') == original


@pytest.mark.asyncio
async def test_source_poetry_survives_without_anthropic(monkeypatch):
    from app import placeholders
    monkeypatch.setattr(placeholders, 'get_settings', lambda: SimpleNamespace(anthropic_api_key=''))
    original = _format_scripture_body('Isaiah 1:2', '<p class="poetry"><b>1:2</b>Listen, O heavens,<p class="poetry">pay attention, O earth!</p>', True, False)
    analyzed = await placeholders._analyze_scripture_with_ai(original, 'Isaiah 1:2')
    rendered = _render_scripture('Isaiah 1:2', ScriptureVersion.NET, analyzed)
    assert '\\begin{poetry}\n\\ch{1}\\vs{2}' in rendered
    assert 'heavens,\npay attention' in rendered


@pytest.mark.skipif(not shutil.which("lualatex"), reason="LuaLaTeX is required")
@pytest.mark.asyncio
async def test_poetry_line_breaks_survive_real_sermon_columns(monkeypatch):
    import pymupdf
    from app.models import SermonOutline, SermonMetadata, SermonPoint
    from app.sermon_latex import generate_sermon_latex
    from app.routes.web import _compile_without_image
    outline = SermonOutline(metadata=SermonMetadata(title="Poetry layout"), main_passage="Isaiah 1:2",
                            points=[SermonPoint(number=1, title="Poetry", content="Notes beside the passage.", scripture_refs=["Isaiah 1:2"])])
    tex = await generate_sermon_latex(outline, include_main_passage=False)
    body = _format_scripture_body('Isaiah 1:2', '<p class="poetry"><b>1:2</b>Alpha<p class="poetry">Beta<p class="poetry">Gamma</p>', True, False)
    async def replace_scripture(work_dir, main_file):
        p = work_dir / main_file
        p.write_text(re.sub(r'\[\[scripture:[^\]]+\]\]', lambda _: _render_scripture('Isaiah 1:2', ScriptureVersion.NET, body), p.read_text()))
    monkeypatch.setattr('app.placeholders.process_scripture_placeholders', replace_scripture)
    pdf, log, _ = await _compile_without_image(tex)
    assert 'Overfull' not in log
    with pymupdf.open(stream=pdf, filetype='pdf') as doc:
        page = next(page for page in doc if page.search_for('Alpha'))
        y = [page.search_for(word)[0].y0 for word in ('Alpha', 'Beta', 'Gamma')]
        assert y[0] < y[1] < y[2], 'Native poetry lines were flattened by the column wrapper'


@pytest.mark.asyncio
@pytest.mark.parametrize('result,accepted', [
    (r'\begin{poetry}\vs{2}For \name{Lord} speaks.\end{poetry}', False),
    (r'\begin{poetry}\vs{3}For the \name{Lord} speaks.\end{poetry}', False),
    (r'\begin{poetry}\vs{2}For the \name{Lord} speaks.\end{poetry}', True),
    (r'\begin{poetry}\vs{2}For the \name{Lord} \hyperlink{strongs-3004}{speaks}.\end{poetry}', True),
    (r'\vs{2}For the LORD speaks!', False),            # punctuation changed
    (r'\vs{2}For the LORD speaks', False),             # punctuation dropped
    (r'\vs{2}for the LORD speaks.', False),            # capitalization changed
    (r'\vs{2}For the LORD Speaks.', False),
    (r'\vs{2}For the \name{God} speaks.', False),      # divine name swapped
    (r'\vs{2}For the \textbf{LORD} speaks.', False),   # unapproved markup
    (r'\vs{2}For the LORD speak s.', False),           # word split
])
async def test_scripture_ai_formatting_cannot_change_words_or_verse_numbers(monkeypatch, result, accepted):
    from app import placeholders
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    original = r'\vs{2}For the LORD speaks.'
    monkeypatch.setattr(placeholders, 'get_settings', lambda: SimpleNamespace(anthropic_api_key='test-only'))
    response = MagicMock()
    response.json.return_value = {'content': [{'type': 'text', 'text': result}]}
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = response
    monkeypatch.setattr(placeholders.httpx, 'AsyncClient', lambda: client)
    actual = await placeholders._analyze_scripture_with_ai(original, 'Isaiah 1:2')
    assert actual == (result if accepted else original)


@pytest.mark.parametrize('result,accepted', [
    (r'\heading{The Day of the \name{Lord}} \begin{poetry}\vs{12}For the \name{Lord} of hosts\end{poetry}', True),
    (r'\heading{The Day of \name{Lord}} \vs{12}For the \name{Lord} of hosts', False),  # "the" dropped
    (r'\heading{The Day of the \name{Lord}} \vs{12}For \name{Lord} of hosts', False),
])
def test_divine_name_tags_inside_headings_keep_exact_wording(result, accepted):
    from app.placeholders import _same_scripture_wording
    assert _same_scripture_wording(r'\heading{The Day of the LORD} \vs{12}For the LORD of hosts', result) is accepted
