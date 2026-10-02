import base64
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pymupdf
import pytest

from app import slides
from app.models import SermonMetadata, SermonOutline, SermonPoint, SermonSubPoint


@pytest.fixture
def pdf():
    with pymupdf.open() as document:
        for _ in range(3):
            page = document.new_page(width=400, height=200)
            page.draw_rect(pymupdf.Rect(100, 50, 300, 150), color=(1, 0, 0), fill=(1, 0, 0))
        return document.tobytes()


@pytest.fixture
def outline():
    return SermonOutline(metadata=SermonMetadata(title="Test"), main_passage="Isaiah 1:1-31", foundational_principle="God saves", points=[
        SermonPoint(number=1, title="Introducing Isaiah", scripture_refs=["Isaiah 1:1"]),
        SermonPoint(number=2, title="Repentance", sub_points=[SermonSubPoint(label="A", title="Conceal", scripture_refs=["John 1:1-5"])]),
    ])


def scripture(**kwargs):
    return slides.SlideItem(id="addition-1", kind="scripture", target="p1.s0", label="Repentance", slide=2, reference="Psalm 51:17", **kwargs)


def visual(**kwargs):
    values = dict(id="addition-2", kind="image", target="p0", label="Timeline", slide=1, bbox=(.25, .25, .75, .75))
    values.update(kwargs)
    return slides.SlideItem(**values)


def analysis(pdf, items, **kwargs):
    values = dict(pdf_sha256=hashlib.sha256(pdf).hexdigest(), page_count=3, items=items, unmatched_slides=[])
    values.update(kwargs)
    return slides.SlideAnalysis(**values)


def test_valid_upload_and_only_rendered_destinations(pdf, outline):
    assert slides.decode_slide_pdf(base64.b64encode(pdf).decode()) == pdf
    assert set(slides.outline_targets(outline)) == {"foundation", "p0", "p1.s0"}
    outline.foundational_principle = None
    assert "foundation" not in slides.outline_targets(outline)


@pytest.mark.parametrize("encoded", ["%%%", base64.b64encode(b"not PDF").decode(), base64.b64encode(b"%PDF-broken").decode()])
def test_rejects_bad_upload(encoded):
    with pytest.raises(slides.SlideError):
        slides.decode_slide_pdf(encoded)


def test_rejects_oversize_before_decoding(monkeypatch):
    monkeypatch.setattr(slides, "MAX_PDF_BYTES", 10)
    with pytest.raises(slides.SlideError, match="10 MB"):
        slides.decode_slide_pdf("A" * 20)


def test_rejects_encrypted_and_too_many_pages(pdf):
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        encrypted = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    with pytest.raises(slides.SlideError, match="password"):
        slides.decode_slide_pdf(base64.b64encode(encrypted).decode())
    with pymupdf.open() as doc:
        for _ in range(101):
            doc.new_page()
        oversized = doc.tobytes()
    with pytest.raises(slides.SlideError, match="100 pages"):
        slides.decode_slide_pdf(base64.b64encode(oversized).decode())


def test_canonicalizes_deduplicates_and_removes_covered_refs(pdf, outline):
    refs = ["Psalm 51:17", "Psalms 51:17", "Isaiah 1:18", "John 1:2-3", "Isaiah 29:13"]
    items = [scripture().model_copy(update={"id": f"ref-{i}", "reference": ref}) for i, ref in enumerate(refs)]
    validated = slides.validate_analysis(analysis(pdf, items), pdf, outline)
    assert [i.reference for i in validated.items] == ["Psalms 51:17", "Isaiah 29:13"]
    assert items[0].reference == "Psalm 51:17"  # Review input is not mutated.


def test_duplicate_reference_on_other_target_is_preserved(pdf, outline):
    items = [scripture(), scripture().model_copy(update={"id": "different", "target": "p0"})]
    assert len(slides.validate_analysis(analysis(pdf, items), pdf, outline).items) == 2


@pytest.mark.parametrize("inner,outer,expected", [("Acts 28:1-10", "Acts 27:1-28:10", True), ("Acts 28:11", "Acts 27:1-28:10", False), ("Isaiah 1:18", "Isaiah 1", True), ("Isaiah 2:1", "Isaiah 1-2", True)])
def test_reference_containment(inner, outer, expected):
    assert slides._contained(inner, outer) is expected


@pytest.mark.parametrize("updates,match", [({"target": "p1"}, "section"), ({"slide": 4}, "outside"), ({"reference": r"Psalm 51:17\input{secret}"}, "Invalid"), ({"reference": "Bogus 1:1"}, "Unknown"), ({"reference": "Isaiah 0:1"}, "invalid"), ({"reference": "Isaiah 2:5-1"}, "invalid"), ({"bbox": (0, 0, 1, 1)}, "no image")])
def test_rejects_invalid_scripture_items(pdf, outline, updates, match):
    with pytest.raises(slides.SlideError, match=match):
        slides.validate_analysis(analysis(pdf, [scripture().model_copy(update=updates)]), pdf, outline)


@pytest.mark.parametrize("bbox", [(-.1, 0, 1, 1), (0, 0, 1.1, 1), (.8, 0, .2, 1), (0, 0, 1, 0), (0, float("nan"), 1, 1)])
def test_rejects_invalid_crops(pdf, outline, bbox):
    item = visual(bbox=bbox)
    with pytest.raises(slides.SlideError, match="crop"):
        slides.validate_analysis(analysis(pdf, [item]), pdf, outline)
    with pytest.raises(slides.SlideError, match="crop"):
        slides.build_slide_assets(pdf, analysis(pdf, [item]))


def test_rejects_stale_analysis_duplicate_ids_and_unmatched_bounds(pdf, outline):
    for value in [analysis(pdf, [], pdf_sha256="0" * 64), analysis(pdf, [], page_count=2), analysis(pdf, [scripture(), scripture()]), analysis(pdf, [], unmatched_slides=[4])]:
        with pytest.raises(slides.SlideError):
            slides.validate_analysis(value, pdf, outline)


def test_source_crop_preserves_pixels_and_omits_disabled_assets(pdf, outline):
    reviewed = slides.validate_analysis(analysis(pdf, [visual(), visual(id="disabled", enabled=False), scripture()]), pdf, outline)
    assets = slides.build_slide_assets(pdf, reviewed)
    assert list(assets) == ["slide-addition-2.png"]
    pixmap = pymupdf.Pixmap(assets["slide-addition-2.png"])
    assert (pixmap.width, pixmap.height) == (500, 250)
    assert pixmap.pixel(250, 125)[:3] == (255, 0, 0)


def test_asset_paths_cannot_escape_directory(pdf):
    unsafe = visual().model_copy(update={"id": "../escape"})
    with pytest.raises(slides.SlideError, match="asset ID"):
        slides.build_slide_assets(pdf, analysis(pdf, [unsafe]))


@pytest.fixture
def anthropic(monkeypatch):
    client = AsyncMock()
    client.__aenter__.return_value = client
    monkeypatch.setattr(slides.httpx, "AsyncClient", lambda: client)
    monkeypatch.setattr(slides, "get_settings", lambda: SimpleNamespace(anthropic_api_key="test-only"))

    def respond(value, stop_reason="end_turn"):
        response = MagicMock()
        response.json.return_value = {"stop_reason": stop_reason, "content": [{"type": "thinking", "thinking": "reasoning is not JSON"}, {"type": "text", "text": value}]}
        client.post.return_value = response
        return client
    return respond


@pytest.mark.asyncio
async def test_analyzes_actual_pdf_document_and_skips_thinking(pdf, outline, anthropic):
    client = anthropic(json.dumps({"items": [scripture().model_dump(), visual().model_dump()], "unmatched_slides": [3]}))
    actual = await slides.analyze_slides(pdf, outline)
    assert actual.pdf_sha256 == hashlib.sha256(pdf).hexdigest()
    assert actual.items[0].reference == "Psalms 51:17"
    assert actual.unmatched_slides == [3]
    payload = client.post.call_args.kwargs["json"]
    assert payload["model"] == "claude-fable-5-1"
    assert payload["fallbacks"] == "default"
    assert client.post.call_args.kwargs["headers"]["anthropic-beta"] == "server-side-fallback-2026-07-01"
    assert payload["output_config"]["effort"] == "medium"
    document = payload["messages"][0]["content"][0]
    assert document["type"] == "document"
    assert base64.b64decode(document["source"]["data"]) == pdf
    assert "p1.s0" in payload["messages"][0]["content"][1]["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("value,stop_reason", [("not JSON", "end_turn"), ('{"items":[]}', "end_turn"), ('{"items":[],"unmatched_slides":[]}', "max_tokens"), ('[]', "end_turn"), ('{"items":[],"unmatched_slides":[],"extra":1}', "end_turn")])
async def test_bad_or_incomplete_model_output_is_explicit(pdf, outline, anthropic, value, stop_reason):
    anthropic(value, stop_reason)
    with pytest.raises(slides.SlideError, match="invalid|incomplete"):
        await slides.analyze_slides(pdf, outline)


@pytest.mark.asyncio
async def test_refusal_is_reported_as_a_decline(pdf, outline, anthropic):
    anthropic("", "refusal")
    with pytest.raises(slides.SlideError, match="declined"):
        await slides.analyze_slides(pdf, outline)


@pytest.mark.asyncio
async def test_missing_key_and_bad_pdf_never_call_anthropic(pdf, outline, anthropic, monkeypatch):
    client = anthropic('{}')
    monkeypatch.setattr(slides, "get_settings", lambda: SimpleNamespace(anthropic_api_key=""))
    with pytest.raises(slides.SlideError, match="API key"):
        await slides.analyze_slides(pdf, outline)
    with pytest.raises(slides.SlideError, match="not a PDF"):
        await slides.analyze_slides(b"invalid", outline)
    client.post.assert_not_called()


def test_enabled_duplicate_wins_over_disabled_first(pdf, outline):
    items = [scripture(enabled=False), scripture().model_copy(update={"id": "enabled-duplicate"})]
    actual = slides.validate_analysis(analysis(pdf, items), pdf, outline)
    assert len(actual.items) == 1
    assert actual.items[0].id == "enabled-duplicate"
    assert actual.items[0].enabled


def test_unmatched_page_numbers_are_strict(pdf):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        analysis(pdf, [], unmatched_slides=[True])


@pytest.mark.asyncio
async def test_api_error_does_not_expose_headers(pdf, outline, anthropic):
    import httpx
    client = anthropic('{}')
    response = httpx.Response(429, request=httpx.Request("POST", slides.ANTHROPIC_MESSAGES_URL, headers={"x-api-key": "secret-never-display"}))
    client.post.side_effect = httpx.HTTPStatusError("sensitive detail", request=response.request, response=response)
    with pytest.raises(slides.SlideError, match="HTTP 429") as error:
        await slides.analyze_slides(pdf, outline)
    assert "secret-never-display" not in str(error.value)
    assert "sensitive detail" not in str(error.value)


@pytest.mark.asyncio
async def test_api_timeout_is_explicit(pdf, outline, anthropic):
    import httpx
    client = anthropic('{}')
    client.post.side_effect = httpx.ReadTimeout("timed out")
    with pytest.raises(slides.SlideError, match="could not complete"):
        await slides.analyze_slides(pdf, outline)


def test_large_page_crop_resolution_is_bounded():
    with pymupdf.open() as doc:
        doc.new_page(width=20000, height=10000)
        data = doc.tobytes()
    value = analysis(data, [visual(bbox=(0, 0, 1, 1))], page_count=1)
    image = pymupdf.Pixmap(slides.build_slide_assets(data, value)["slide-addition-2.png"])
    assert max(image.width, image.height) <= 1600
