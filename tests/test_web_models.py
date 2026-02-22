from app.routes.web import (
    ExtractRequest, ExtractResponse, ExtractCandidateEntry,
    ExtractCandidateSource, SelectedCommentaryEntry,
    SelectedCommentaryResult, GenerateRequest,
)


def test_extract_request_defaults():
    req = ExtractRequest(notes="James 3")
    assert req.commentaries == []
    assert req.image is None


def test_extract_response_with_candidates():
    resp = ExtractResponse(
        success=True,
        candidates={
            "mhc": ExtractCandidateSource(
                source_name="Matthew Henry",
                entries=[ExtractCandidateEntry(verse_start=1, verse_end=3, text="Test")]
            )
        }
    )
    assert resp.candidates["mhc"].source_name == "Matthew Henry"
    assert resp.candidates["mhc"].entries[0].text == "Test"


def test_generate_request_accepts_overrides():
    req = GenerateRequest(
        notes="test",
        commentary_overrides=[
            SelectedCommentaryResult(
                source_name="Matthew Henry",
                entries=[SelectedCommentaryEntry(verse_start=1, verse_end=2, text="txt")]
            )
        ]
    )
    assert len(req.commentary_overrides) == 1
    assert req.outline is None


def test_generate_request_backward_compat():
    """Old clients omitting new fields still work."""
    req = GenerateRequest(notes="test")
    assert req.commentary_overrides == []
    assert req.outline is None
