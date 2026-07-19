import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def stored_doc(tmp_path, monkeypatch):
    """A PDF + TeX pair saved in a temp storage dir, returns the pdf_id."""

    class _Settings:
        storage_path = str(tmp_path)
        pdf_retention_days = 7

    monkeypatch.setattr("app.storage.get_settings", lambda: _Settings())
    doc_dir = tmp_path / "outputs" / "test-id-123"
    doc_dir.mkdir(parents=True)
    (doc_dir / "Sermon.pdf").write_bytes(b"%PDF-1.7 fake pdf bytes")
    (doc_dir / "Sermon.tex").write_text("\\documentclass{article}")
    return "test-id-123"


def test_download_tex_returns_tex_source(client, stored_doc):
    resp = client.get(f"/download/{stored_doc}/tex")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-tex")
    assert resp.content == b"\\documentclass{article}"


def test_download_pdf_with_slug_returns_pdf(client, stored_doc):
    resp = client.get(f"/download/{stored_doc}/Sermon.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


def test_host_0000_redirects_to_localhost():
    with TestClient(app, base_url="http://0.0.0.0:8000") as c:
        resp = c.get("/health?probe=1", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "http://localhost:8000/health?probe=1"


def test_other_hosts_are_not_redirected(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 200
