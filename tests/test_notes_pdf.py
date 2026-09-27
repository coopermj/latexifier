import base64
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import llm
from app.main import app
from app.models import SermonMetadata, SermonOutline, Table
from app.sermon_latex import _render_table

MOCK_OUTLINE = SermonOutline(
    metadata=SermonMetadata(title="The Darkness of Pride"),
    main_passage="Isaiah 2:6-22",
    points=[],
    tables=[Table(headers=["Pride: Self-Focus", "Humility: God-Focus"], rows=[["Takes credit", "Gives credit"]])],
)
PDF_B64 = base64.b64encode(b"%PDF-1.7 notes").decode()


def _post(path, body, **patches):
    with (
        patch("app.routes.web.extract_sermon_outline", new_callable=AsyncMock, return_value=MOCK_OUTLINE) as pdf_extract,
        patch("app.routes.web.extract_sermon_outline_from_text", new_callable=AsyncMock, return_value=MOCK_OUTLINE) as text_extract,
        patch("app.routes.web._valid_sessions", {"tok"}),
    ):
        with TestClient(app) as client:
            client.cookies.set("session", "tok")
            resp = client.post(path, json=body)
    return resp, pdf_extract, text_extract


def test_extract_accepts_notes_pdf_without_pasted_text():
    resp, pdf_extract, text_extract = _post("/web/extract", {"notes_pdf": PDF_B64})
    data = resp.json()
    assert data["success"] is True
    assert data["outline"]["tables"][0]["rows"] == [["Takes credit", "Gives credit"]]
    pdf_extract.assert_awaited_once_with(b"%PDF-1.7 notes", None)
    text_extract.assert_not_called()


def test_extract_passes_pasted_text_as_context_for_pdf():
    _, pdf_extract, _ = _post("/web/extract", {"notes": "extra", "notes_pdf": PDF_B64})
    pdf_extract.assert_awaited_once_with(b"%PDF-1.7 notes", "extra")


def test_extract_rejects_non_pdf_upload():
    resp, pdf_extract, _ = _post("/web/extract", {"notes_pdf": base64.b64encode(b"hello").decode()})
    assert resp.json() == {**resp.json(), "success": False, "error": "The sermon notes file is not a PDF."}
    pdf_extract.assert_not_called()


def test_extract_requires_notes_or_pdf():
    resp, _, _ = _post("/web/extract", {"notes": "  "})
    assert resp.json()["error"] == "No sermon notes provided"


def test_generate_accepts_outline_without_notes_text():
    with (
        patch("app.routes.web.generate_sermon_latex", new_callable=AsyncMock, return_value="\\documentclass{article}"),
        patch("app.routes.web._compile_without_image", new_callable=AsyncMock, return_value=(b"%PDF", "", "tex")),
        patch("app.routes.web.save_pdf", new_callable=AsyncMock, return_value="abc"),
    ):
        resp, pdf_extract, text_extract = _post("/web/generate", {"outline": MOCK_OUTLINE.model_dump()})
    assert resp.json()["success"] is True
    pdf_extract.assert_not_called()
    text_extract.assert_not_called()


def test_pdf_prompt_includes_layout_and_table_guidance():
    prompt = llm._pdf_prompt("pasted extra")
    assert "NOT pipe-delimited" in prompt
    assert "pasted extra" in prompt
    assert "SUPPLEMENTARY" not in llm._pdf_prompt(None)


def test_render_table_uses_breakable_table_with_repeating_header():
    tex = "\n".join(_render_table(Table(headers=["A & B", "C"], rows=[["1", "2", "extra"], ["3"]], caption="Pride vs Humility")))
    assert r"\begin{xltabular}{\textwidth}" in tex
    assert r"\endhead" in tex
    assert r"A \& B" in tex
    assert r"1 & 2 \\" in tex  # extra cells are dropped
    assert r"3 &  \\" in tex   # short rows are padded
    assert "Pride vs Humility" in tex
