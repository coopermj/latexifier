import pytest
import hashlib
import shutil
import pymupdf

from app.models import SermonOutline, SermonMetadata, SermonPoint, SermonSubPoint
from app.slides import SlideAnalysis, SlideItem
from app.sermon_latex import generate_sermon_latex


@pytest.mark.asyncio
async def test_slide_additions_render_at_their_matching_section():
    outline = SermonOutline(metadata=SermonMetadata(title="Slides"), main_passage="Isaiah 1:1-31",
        points=[SermonPoint(number=1, title="Introducing Isaiah", content="Introduction", scripture_refs=["Isaiah 1:1"]),
                SermonPoint(number=2, title="Rebellion", sub_points=[
                    SermonSubPoint(label="A", title="Confrontation", content="Conviction", scripture_verse="Isaiah 1:2"),
                    SermonSubPoint(label="B", title="Grace", content="Mercy", scripture_verse="Isaiah 1:9")])])
    analysis = SlideAnalysis(pdf_sha256="a" * 64, page_count=4, items=[
        SlideItem(id="timeline", kind="image", target="p0", label="Kings & prophets", slide=1, bbox=[0, 0, 1, 1]),
        SlideItem(id="grace", kind="scripture", target="p1.s1", label="Mercy", slide=2, reference="Habakkuk 3:2"),
        SlideItem(id="table", kind="table", target="p1.s0", label="Two responses", slide=3, bbox=[0, 0, 1, 1]),
        SlideItem(id="excluded", kind="scripture", target="p1.s0", label="Excluded", slide=4, reference="Titus 2:14", enabled=False),
    ], unmatched_slides=[])
    tex = await generate_sermon_latex(outline, include_main_passage=False, slide_analysis=analysis)
    assert tex.index("Kings \\& prophets") < tex.index("Introduction")
    assert tex.index("A. Confrontation") < tex.index("Two responses") < tex.index("B. Grace")
    assert tex.index("B. Grace") < tex.index("Habakkuk 3:2")
    assert "Titus 2:14" not in tex
    assert "slide-timeline.png" in tex
    assert "slide-table.png" in tex
    assert "Slide 2" in tex
    assert "[[scripture:Habakkuk 3:2" in tex


@pytest.mark.asyncio
async def test_absent_slide_analysis_does_not_change_output():
    outline = SermonOutline(metadata=SermonMetadata(title="Test"), main_passage="Isaiah 1:1", points=[])
    assert await generate_sermon_latex(outline) == await generate_sermon_latex(outline, slide_analysis=None)


@pytest.mark.skipif(not shutil.which("lualatex"), reason="LuaLaTeX is required")
@pytest.mark.asyncio
async def test_source_table_crop_and_pullout_compile_without_overflow(monkeypatch):
    from app.slides import build_slide_assets
    from app.sermon_latex import _render_slide_scriptures, _render_slide_visuals
    from app.routes.web import _compile_without_image
    from pathlib import Path

    with pymupdf.open() as source:
        page = source.new_page(width=500, height=200)
        page.draw_rect((10, 10, 490, 190))
        page.draw_line((250, 10), (250, 190))
        page.draw_line((10, 65), (490, 65))
        page.insert_text((25, 40), "Conceal", fontsize=20)
        page.insert_text((270, 40), "Confess", fontsize=20)
        page.insert_text((25, 110), "Compounds guilt", fontsize=17)
        page.insert_text((270, 110), "Cleanses guilt", fontsize=17)
        pdf = source.tobytes()
    analysis = SlideAnalysis(pdf_sha256=hashlib.sha256(pdf).hexdigest(), page_count=1, items=[
        SlideItem(id="table", kind="table", target="p0", label="Conceal & confess", slide=1, bbox=[0, 0, 1, 1]),
        SlideItem(id="verse", kind="scripture", target="p0", label="Mercy", slide=1, reference="Habakkuk 3:2"),
    ])
    tex = (Path(__file__).parent / "fixtures/scripture_typography.tex").read_text()
    additions = "\n".join(_render_slide_visuals(analysis.items) + _render_slide_scriptures(analysis.items, "NET"))
    tex = tex.replace(r"\end{document}", "\\newpage\n" + additions + r"\end{document}")
    # Exercise the real renderer/compiler with deterministic Scripture; no paid calls in tests.
    async def scripture(work_dir, main_file):
        p = work_dir / main_file
        import re
        p.write_text(re.sub(r"\[\[scripture:[^\]]+\]\]", lambda _: r"\begin{scripture}[Habakkuk 3:2]\ch{3}\vs{2}In wrath remember mercy.\end{scripture}", p.read_text()))
    monkeypatch.setattr("app.placeholders.process_scripture_placeholders", scripture)
    # The fixture uses a different accent name from the sermon template.
    tex = tex.replace(r"\begin{document}", r"\definecolor{highlight}{rgb}{0.4,0,0.4}\begin{document}")
    rendered, log, _ = await _compile_without_image(tex, supplementary_pdfs=build_slide_assets(pdf, analysis))
    assert "Overfull" not in log
    assert "Missing character" not in log
    with pymupdf.open(stream=rendered, filetype="pdf") as document:
        last = document[-1]
        assert last.get_images()
        assert "Conceal & confess" in last.get_text()
        assert "remember mercy" in last.get_text()
