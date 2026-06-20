from pathlib import Path


def test_anthropic_sonnet_model_is_current_non_retired_snapshot():
    from app import llm, placeholders

    assert llm.ANTHROPIC_SONNET_MODEL == "claude-sonnet-4-6"
    assert placeholders.ANTHROPIC_SONNET_MODEL == llm.ANTHROPIC_SONNET_MODEL


def test_retired_sonnet_4_snapshot_is_not_used_in_api_callers():
    api_callers = (
        Path("app/llm.py").read_text(),
        Path("app/placeholders.py").read_text(),
    )

    for source in api_callers:
        assert "claude-sonnet-4-20250514" not in source
