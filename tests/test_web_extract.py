from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.models import SermonOutline, SermonMetadata
from app.commentary import CommentaryResult, CommentarySource, CommentaryEntry

MOCK_OUTLINE = SermonOutline(
    metadata=SermonMetadata(title="Test Sermon", speaker="Pastor Test", date="Jan 1, 2026"),
    main_passage="James 3:1",
    points=[],
    all_scripture_refs=[],
)

MOCK_COMMENTARY = CommentaryResult(
    source=CommentarySource.MHC,
    source_name="Matthew Henry's Complete Commentary",
    book="James", chapter=3, verse=1,
    entries=[CommentaryEntry(verse_start=1, verse_end=2, text="Test entry text.")],
)


def test_extract_requires_auth():
    mock_settings = MagicMock()
    mock_settings.is_development = False
    with patch("app.routes.web.get_settings", return_value=mock_settings):
        with TestClient(app) as client:
            resp = client.post("/web/extract", json={"notes": "test"})
            assert resp.status_code == 401


def test_extract_returns_outline_and_candidates():
    with (
        patch("app.routes.web.extract_sermon_outline_from_text", new_callable=AsyncMock) as mock_extract,
        patch("app.routes.web.fetch_commentary_for_reference", new_callable=AsyncMock) as mock_commentary,
        patch("app.routes.web._valid_sessions", {"test-token"}),
    ):
        mock_extract.return_value = MOCK_OUTLINE
        mock_commentary.return_value = MOCK_COMMENTARY

        with TestClient(app) as client:
            client.cookies.set("session", "test-token")
            resp = client.post("/web/extract", json={
                "notes": "James 3:1-12\nTest sermon",
                "commentaries": ["mhc"],
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["outline"]["metadata"]["title"] == "Test Sermon"
        assert "mhc" in data["candidates"]
        assert data["candidates"]["mhc"]["source_name"] == "Matthew Henry's Complete Commentary"
        assert data["candidates"]["mhc"]["entries"][0]["text"] == "Test entry text."
