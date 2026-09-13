import base64
import hashlib
from unittest.mock import AsyncMock, patch

import pymupdf
from fastapi.testclient import TestClient

from app.main import app
from app.models import SermonOutline, SermonMetadata, SermonPoint
from app.slides import SlideAnalysis, SlideItem


def slide_fixture():
    doc = pymupdf.open()
    page = doc.new_page(width=960, height=540)
    page.insert_text((40, 40), "Psalm 51:17")
    pdf = doc.tobytes()
    doc.close()
    analysis = SlideAnalysis(pdf_sha256=hashlib.sha256(pdf).hexdigest(), page_count=1, items=[
        SlideItem(id="one", kind="scripture", target="p0", label="Repentance", slide=1, reference="Psalms 51:17"),
        SlideItem(id="two", kind="table", target="p0", label="Table", slide=1, bbox=[0, 0, 1, 1]),
    ], unmatched_slides=[])
    outline = SermonOutline(metadata=SermonMetadata(title="Test"), main_passage="Isaiah 1:1-31",
                            points=[SermonPoint(number=1, title="Repentance")])
    return pdf, analysis, outline


def test_extract_returns_slide_matches():
    pdf, analysis, outline = slide_fixture()
    with patch("app.routes.web._valid_sessions", {"tok"}), \
         patch("app.routes.web.extract_sermon_outline_from_text", new_callable=AsyncMock, return_value=outline), \
         patch("app.routes.web.analyze_slides", new_callable=AsyncMock, return_value=analysis) as analyze:
        with TestClient(app) as client:
            client.cookies.set("session", "tok")
            response = client.post("/web/extract", json={"notes": "notes", "slides_pdf": base64.b64encode(pdf).decode()})
        assert response.json()["success"]
        assert response.json()["slide_analysis"]["items"][0]["reference"] == "Psalms 51:17"
        analyze.assert_awaited_once_with(pdf, outline)


def test_invalid_upload_rejected_before_paid_extraction():
    with patch("app.routes.web._valid_sessions", {"tok"}), \
         patch("app.routes.web.extract_sermon_outline_from_text", new_callable=AsyncMock) as extract:
        with TestClient(app) as client:
            client.cookies.set("session", "tok")
            response = client.post("/web/extract", json={"notes": "notes", "slides_pdf": "not a PDF"})
        assert not response.json()["success"]
        extract.assert_not_awaited()


def test_generate_reuses_review_and_passes_original_crop_to_compiler():
    pdf, analysis, outline = slide_fixture()
    analysis.items[0].enabled = False
    with patch("app.routes.web._valid_sessions", {"tok"}), \
         patch("app.routes.web.analyze_slides", new_callable=AsyncMock) as analyze, \
         patch("app.routes.web.generate_sermon_latex", new_callable=AsyncMock, return_value="latex") as render, \
         patch("app.routes.web._compile_without_image", new_callable=AsyncMock, return_value=(b"pdf", "", "tex")) as compile, \
         patch("app.routes.web.save_pdf", new_callable=AsyncMock, return_value="test"):
        with TestClient(app) as client:
            client.cookies.set("session", "tok")
            response = client.post("/web/generate", json={"notes": "notes", "outline": outline.model_dump(),
                "slides_pdf": base64.b64encode(pdf).decode(), "slide_analysis": analysis.model_dump()})
        assert response.json()["success"], response.json()
        analyze.assert_not_awaited()
        assert not render.call_args.kwargs["slide_analysis"].items[0].enabled
        assets = compile.call_args.kwargs["supplementary_pdfs"]
        assert assets["slide-two.png"].startswith(b"\x89PNG")


def test_generate_rejects_stale_analysis_and_missing_original():
    pdf, analysis, outline = slide_fixture()
    analysis.pdf_sha256 = "0" * 64
    with patch("app.routes.web._valid_sessions", {"tok"}), \
         patch("app.routes.web.generate_sermon_latex", new_callable=AsyncMock) as render:
        with TestClient(app) as client:
            client.cookies.set("session", "tok")
            for slides in (None, base64.b64encode(pdf).decode()):
                response = client.post("/web/generate", json={"notes": "notes", "outline": outline.model_dump(),
                    "slides_pdf": slides, "slide_analysis": analysis.model_dump()})
                assert not response.json()["success"]
                assert response.json()["error"]
        render.assert_not_awaited()


def test_no_slides_does_not_call_anthropic_slide_analysis():
    _, _, outline = slide_fixture()
    with patch("app.routes.web._valid_sessions", {"tok"}), \
         patch("app.routes.web.extract_sermon_outline_from_text", new_callable=AsyncMock, return_value=outline), \
         patch("app.routes.web.analyze_slides", new_callable=AsyncMock) as analyze:
        with TestClient(app) as client:
            client.cookies.set("session", "tok")
            response = client.post("/web/extract", json={"notes": "notes"})
        assert response.json()["success"]
        assert response.json()["slide_analysis"] is None
        analyze.assert_not_awaited()


def test_missing_slide_scripture_cannot_publish_an_empty_pullout():
    pdf, analysis, outline = slide_fixture()
    for marker in ("% [scripture not found: Psalms 51:17]", "% [scripture error: Psalms 51:17]"):
        with patch("app.routes.web._valid_sessions", {"tok"}), \
             patch("app.routes.web.generate_sermon_latex", new_callable=AsyncMock, return_value="latex"), \
             patch("app.routes.web._compile_without_image", new_callable=AsyncMock, return_value=(b"pdf", "", marker)), \
             patch("app.routes.web.save_pdf", new_callable=AsyncMock) as save:
            with TestClient(app) as client:
                client.cookies.set("session", "tok")
                response = client.post("/web/generate", json={"notes": "notes", "outline": outline.model_dump(),
                    "slides_pdf": base64.b64encode(pdf).decode(), "slide_analysis": analysis.model_dump()})
            assert not response.json()["success"]
            assert "Psalms 51:17" in response.json()["error"]
            save.assert_not_awaited()
