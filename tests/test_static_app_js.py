from pathlib import Path


APP_JS = Path("app/static/app.js").read_text(encoding="utf-8")


def _start_over_handler() -> str:
    start = APP_JS.index("document.getElementById('start-over-btn').addEventListener")
    end = APP_JS.index("function collectEditedOutline", start)
    return APP_JS[start:end]


def test_start_over_clears_review_outline_state() -> None:
    handler = _start_over_handler()

    assert "outline-summary').innerHTML = ''" in handler
    assert "commentary-cards').innerHTML = ''" in handler
    assert "review-error').classList.add('hidden')" in handler
    assert "review-error-message').textContent = ''" in handler
