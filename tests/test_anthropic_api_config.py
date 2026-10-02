import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import llm, placeholders
from app.models import SermonOutline, SermonMetadata, SermonPoint


def test_all_anthropic_callers_use_fable():
    from app.anthropic_config import ANTHROPIC_MODEL

    assert ANTHROPIC_MODEL == 'claude-fable-5-1'
    assert llm.ANTHROPIC_MODEL == placeholders.ANTHROPIC_MODEL == ANTHROPIC_MODEL
    for path in ['app/llm.py', 'app/placeholders.py', 'app/anthropic_config.py']:
        source = Path(path).read_text()
        assert 'claude-sonnet-' not in source
        assert 'claude-haiku-' not in source


@pytest.fixture
def anthropic_response(monkeypatch):
    client = AsyncMock()
    client.__aenter__.return_value = client
    monkeypatch.setattr(llm.httpx, 'AsyncClient', lambda: client)
    settings = SimpleNamespace(anthropic_api_key='test-only')
    monkeypatch.setattr(llm, 'get_settings', lambda: settings)
    monkeypatch.setattr(placeholders, 'get_settings', lambda: settings)

    def respond(text):
        response = MagicMock()
        response.json.return_value = {
            'content': [
                {'type': 'thinking', 'thinking': 'test reasoning', 'signature': 'test'},
                {'type': 'text', 'text': text},
            ],
            'stop_reason': 'end_turn',
        }
        client.post.return_value = response
        return client
    return respond


def assert_fable_request(client):
    kwargs = client.post.call_args.kwargs
    payload = kwargs['json']
    assert payload['model'] == 'claude-fable-5-1'
    assert payload['fallbacks'] == 'default'
    assert kwargs['headers']['anthropic-beta'] == 'server-side-fallback-2026-07-01'
    assert payload['max_tokens'] >= 2048
    assert payload['output_config']['effort'] in {'low', 'medium'}
    assert 'thinking' not in payload  # Fable's adaptive thinking is always on.
    assert kwargs['timeout'] >= 60


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['text', 'pdf'])
async def test_fable_extraction_handles_thinking_before_json(anthropic_response, monkeypatch, source):
    expected = SermonOutline(metadata=SermonMetadata(title='Rebels and Their Redeemer'), main_passage='Isaiah 1:1-31', points=[])
    client = anthropic_response(expected.model_dump_json())
    monkeypatch.setattr(llm, '_normalize_scripture_refs', AsyncMock(side_effect=lambda outline: outline))
    monkeypatch.setattr(llm, '_assign_missing_verse_refs', AsyncMock(side_effect=lambda outline: outline))
    actual = await (llm.extract_sermon_outline_from_text('Sermon notes') if source == 'text' else llm.extract_sermon_outline(b'%PDF-test'))
    assert actual == expected
    assert_fable_request(client)


@pytest.mark.asyncio
async def test_fable_normalization_uses_text_after_thinking(anthropic_response):
    outline = SermonOutline(metadata=SermonMetadata(title='Test'), main_passage='Isaiah 1:1-31', points=[SermonPoint(number=1, title='Repentance', scripture_refs=['vv. 10-20'])])
    client = anthropic_response(json.dumps({'p0.r0': 'Isaiah 1:10-20'}))
    actual = await llm._normalize_scripture_refs(outline)
    assert actual.points[0].scripture_refs == ['Isaiah 1:10-20']
    assert_fable_request(client)


@pytest.mark.asyncio
async def test_fable_assignment_uses_text_after_thinking(anthropic_response):
    outline = SermonOutline(metadata=SermonMetadata(title='Test'), main_passage='Isaiah 1:1-31', points=[SermonPoint(number=1, title='Repentance')])
    client = anthropic_response(json.dumps({'p0': 'Isaiah 1:10-20'}))
    actual = await llm._assign_missing_verse_refs(outline)
    assert actual.points[0].scripture_refs == ['Isaiah 1:10-20']
    assert_fable_request(client)


@pytest.mark.asyncio
async def test_fable_scripture_formatting_uses_text_after_thinking(anthropic_response):
    original = r'\vs{18}“Come now,” says the Lord.'
    formatted = r'\begin{poetry}\vs{18}“Come now,” says the \name{Lord}.\end{poetry}'
    client = anthropic_response(formatted)
    assert await placeholders._analyze_scripture_with_ai(original, 'Isaiah 1:18') == formatted
    assert_fable_request(client)


def _refusal(client):
    response = MagicMock()
    response.json.return_value = {'content': [], 'stop_reason': 'refusal', 'stop_details': {'type': 'refusal', 'category': 'cyber'}}
    client.post.return_value = response


@pytest.mark.asyncio
@pytest.mark.parametrize('source', ['text', 'pdf'])
async def test_extraction_refusal_gives_clear_error(anthropic_response, source):
    client = anthropic_response('unused')
    _refusal(client)
    with pytest.raises(llm.LLMError, match='declined'):
        await (llm.extract_sermon_outline_from_text('Sermon notes') if source == 'text' else llm.extract_sermon_outline(b'%PDF-test'))
    assert_fable_request(client)


@pytest.mark.asyncio
async def test_scripture_formatting_refusal_keeps_original_text(anthropic_response):
    client = anthropic_response('unused')
    _refusal(client)
    original = r'\vs{18}“Come now,” says the Lord.'
    assert await placeholders._analyze_scripture_with_ai(original, 'Isaiah 1:18') == original
    assert_fable_request(client)


@pytest.mark.asyncio
async def test_ref_normalization_refusal_keeps_outline(anthropic_response):
    outline = SermonOutline(metadata=SermonMetadata(title='Test'), main_passage='Isaiah 1:1-31', points=[SermonPoint(number=1, title='Repentance', scripture_refs=['vv. 10-20'])])
    client = anthropic_response('unused')
    _refusal(client)
    assert await llm._normalize_scripture_refs(outline) == outline
