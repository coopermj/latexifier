from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.models import SermonOutline, SermonMetadata


MOCK_OUTLINE = SermonOutline(
    metadata=SermonMetadata(title="Test", speaker=None, date=None),
    main_passage="James 3:1",
    points=[],
    all_scripture_refs=[],
)


def test_generate_uses_preextracted_outline_skipping_llm():
    """When outline is provided in request, LLM extraction is not called."""
    fake_pdf = b"%PDF-1.4 fake"
    with (
        patch("app.routes.web.extract_sermon_outline_from_text", new_callable=AsyncMock) as mock_llm,
        patch("app.routes.web.generate_sermon_latex", new_callable=AsyncMock) as mock_latex,
        patch("app.routes.web._compile_without_image", new_callable=AsyncMock) as mock_compile,
        patch("app.routes.web.save_pdf", new_callable=AsyncMock) as mock_save,
        patch("app.routes.web._valid_sessions", {"tok"}),
    ):
        mock_latex.return_value = "\\documentclass{article}"
        mock_compile.return_value = (fake_pdf, "", "\\documentclass{article}")
        mock_save.return_value = "abc123"

        with TestClient(app) as client:
            client.cookies.set("session", "tok")
            resp = client.post("/web/generate", json={
                "notes": "ignored",
                "outline": MOCK_OUTLINE.model_dump(),
            })

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_llm.assert_not_called()


def test_generate_passes_overrides_to_sermon_latex():
    """commentary_overrides are converted to CommentaryResult and passed to generate_sermon_latex."""
    fake_pdf = b"%PDF-1.4 fake"
    with (
        patch("app.routes.web.generate_sermon_latex", new_callable=AsyncMock) as mock_latex,
        patch("app.routes.web._compile_without_image", new_callable=AsyncMock) as mock_compile,
        patch("app.routes.web.save_pdf", new_callable=AsyncMock) as mock_save,
        patch("app.routes.web._valid_sessions", {"tok"}),
    ):
        mock_latex.return_value = "\\documentclass{article}"
        mock_compile.return_value = (fake_pdf, "", "\\documentclass{article}")
        mock_save.return_value = "abc123"

        with TestClient(app) as client:
            client.cookies.set("session", "tok")
            resp = client.post("/web/generate", json={
                "notes": "ignored",
                "outline": MOCK_OUTLINE.model_dump(),
                "commentary_overrides": [
                    {
                        "source_name": "Matthew Henry",
                        "entries": [{"verse_start": 1, "verse_end": 2, "text": "Test."}]
                    }
                ],
            })

        assert resp.status_code == 200
        call_kwargs = mock_latex.call_args.kwargs
        assert call_kwargs.get("commentary_overrides") is not None
        assert len(call_kwargs["commentary_overrides"]) == 1
        assert call_kwargs["commentary_overrides"][0].source_name == "Matthew Henry"
