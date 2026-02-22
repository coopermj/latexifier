# Commentary Review Wizard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a three-step wizard (Input → Review Commentary → Done) so users can see and select specific commentary excerpts before generating the PDF.

**Architecture:** Split the current single `/web/generate` call into `/web/extract` (Claude + commentary fetch) and a modified `/web/generate` (accepts pre-selected commentary). All wizard state lives in the browser. Backend changes are backward-compatible — the old one-shot path still works.

**Tech Stack:** FastAPI, Pydantic v2, vanilla HTML/JS/CSS (no frameworks), pytest + pytest-asyncio + httpx for backend tests.

---

### Task 1: Set up test infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `requirements.txt`

**Step 1: Add test dependencies to requirements.txt**

Append these lines to the end of `requirements.txt`:
```
pytest>=8.0.0
pytest-asyncio>=0.24.0
httpx>=0.27.0
```

**Step 2: Install them**

```bash
pip install pytest pytest-asyncio "httpx>=0.27.0"
```

**Step 3: Create `tests/__init__.py`** (empty file)

**Step 4: Create `tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
```

**Step 5: Verify pytest runs**

```bash
cd /Users/micahcooper/latexgen && python -m pytest tests/ -v
```

Expected: `no tests ran` (no errors)

**Step 6: Commit**

```bash
git add requirements.txt tests/
git commit -m "chore: add pytest test infrastructure"
```

---

### Task 2: Add `commentary_overrides` to `sermon_latex.py`

This lets the caller pass pre-fetched `CommentaryResult` objects directly, bypassing the DB fetch. Used by the wizard generate path.

**Files:**
- Modify: `app/sermon_latex.py` (function signatures only, ~lines 112–121 and 635–638)
- Create: `tests/test_sermon_latex.py`

**Step 1: Write the failing test**

Create `tests/test_sermon_latex.py`:

```python
import pytest
from app.commentary import CommentaryResult, CommentarySource, CommentaryEntry
from app.sermon_latex import _render_commentary_appendix


@pytest.mark.asyncio
async def test_render_commentary_appendix_uses_preloaded():
    """When preloaded results are passed, they are rendered without fetching DB."""
    entry = CommentaryEntry(verse_start=1, verse_end=3, text="Test commentary text.")
    result = CommentaryResult(
        source=CommentarySource.MHC,
        source_name="Matthew Henry",
        book="James", chapter=3, verse=1,
        entries=[entry],
    )
    lines = await _render_commentary_appendix(
        main_passage="James 3:1",
        commentary_sources=[],
        preloaded=[result],
    )
    combined = "\n".join(lines)
    assert "Matthew Henry" in combined
    assert "Test commentary text." in combined


@pytest.mark.asyncio
async def test_render_commentary_appendix_empty_when_no_sources_and_no_preloaded():
    lines = await _render_commentary_appendix(
        main_passage="James 3:1",
        commentary_sources=[],
        preloaded=None,
    )
    assert lines == []
```

**Step 2: Run test — expect failure**

```bash
python -m pytest tests/test_sermon_latex.py -v
```

Expected: `TypeError` — `_render_commentary_appendix` doesn't accept `preloaded` yet.

**Step 3: Add `preloaded` parameter to `_render_commentary_appendix` in `app/sermon_latex.py`**

Change the signature (line ~637):
```python
async def _render_commentary_appendix(
    main_passage: str,
    commentary_sources: list[str],
    preloaded: list[CommentaryResult] | None = None,
) -> list[str]:
```

Then replace the existing fetch block (lines ~657–670) with:
```python
    if preloaded is not None:
        commentaries = preloaded
    else:
        # Fetch commentary for the main passage from each source
        commentaries: list[CommentaryResult] = []
        for source in sources:
            logger.info("Fetching commentary from %s for %s", source.value, main_passage)
            result = await fetch_commentary_for_reference(main_passage, source)
            if result:
                logger.info("Got commentary result with %d entries", len(result.entries))
                commentaries.append(result)
            else:
                logger.warning("No commentary result from %s", source.value)
```

Also update the call site in `generate_sermon_latex` (line ~413) to pass a new `commentary_overrides` parameter:

Change `generate_sermon_latex` signature (add after `commentary_sources` parameter):
```python
    commentary_overrides: list[CommentaryResult] | None = None,
```

Change the call at line ~414:
```python
    if commentary_sources or commentary_overrides is not None:
        commentary_lines = await _render_commentary_appendix(
            main_passage,
            commentary_sources or [],
            preloaded=commentary_overrides,
        )
        lines.extend(commentary_lines)
```

**Step 4: Run test — expect pass**

```bash
python -m pytest tests/test_sermon_latex.py -v
```

Expected: 2 PASSED

**Step 5: Commit**

```bash
git add app/sermon_latex.py tests/test_sermon_latex.py
git commit -m "feat: add commentary_overrides bypass to sermon_latex"
```

---

### Task 3: Add new Pydantic models to `app/routes/web.py`

**Files:**
- Modify: `app/routes/web.py` (top section, models only)
- Create: `tests/test_web_models.py`

**Step 1: Write the failing test**

Create `tests/test_web_models.py`:

```python
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
```

**Step 2: Run test — expect failure**

```bash
python -m pytest tests/test_web_models.py -v
```

Expected: `ImportError` — new models don't exist yet.

**Step 3: Add models to `app/routes/web.py`**

Add these classes after the existing `AuthResponse` class (before `GenerateRequest`):

```python
class ExtractCandidateEntry(BaseModel):
    verse_start: int
    verse_end: int | None = None
    text: str


class ExtractCandidateSource(BaseModel):
    source_name: str
    entries: list[ExtractCandidateEntry]


class ExtractRequest(BaseModel):
    notes: str
    image: str | None = None
    commentaries: list[str] = []


class ExtractResponse(BaseModel):
    success: bool
    outline: dict | None = None          # SermonOutline.model_dump()
    candidates: dict[str, ExtractCandidateSource] = {}  # {source_key: ExtractCandidateSource}
    error: str | None = None


class SelectedCommentaryEntry(BaseModel):
    verse_start: int
    verse_end: int | None = None
    text: str


class SelectedCommentaryResult(BaseModel):
    source_name: str
    entries: list[SelectedCommentaryEntry]
```

Then modify `GenerateRequest` to add two new optional fields at the end:

```python
class GenerateRequest(BaseModel):
    notes: str
    image: str | None = None
    commentaries: list[str] = []
    bulletin_pdf: str | None = None
    prayer_pdf: str | None = None
    outline: dict | None = None                              # pre-extracted SermonOutline
    commentary_overrides: list[SelectedCommentaryResult] = []  # user-selected entries
```

**Step 4: Run test — expect pass**

```bash
python -m pytest tests/test_web_models.py -v
```

Expected: 4 PASSED

**Step 5: Commit**

```bash
git add app/routes/web.py tests/test_web_models.py
git commit -m "feat: add extract/commentary-override models to web router"
```

---

### Task 4: Add `POST /web/extract` endpoint

**Files:**
- Modify: `app/routes/web.py` (add endpoint after `/auth`)
- Create: `tests/test_web_extract.py`

**Step 1: Write the failing test**

Create `tests/test_web_extract.py`:

```python
from unittest.mock import AsyncMock, patch
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
```

**Step 2: Run test — expect failure**

```bash
python -m pytest tests/test_web_extract.py -v
```

Expected: 404 or `ImportError` — endpoint doesn't exist yet.

**Step 3: Add the `POST /web/extract` endpoint to `app/routes/web.py`**

Add this import at the top of the file (with existing imports):
```python
from ..commentary import CommentarySource, fetch_commentary_for_reference
```

Add the endpoint after the `authenticate` function:

```python
@router.post("/extract", response_model=ExtractResponse)
async def extract_sermon(
    request: ExtractRequest,
    session: str | None = Cookie(default=None)
):
    """Extract sermon outline and fetch commentary candidates."""
    settings = get_settings()

    if not settings.is_development:
        if not session or session not in _valid_sessions:
            raise HTTPException(status_code=401, detail="Not authenticated")

    if not request.notes or not request.notes.strip():
        return ExtractResponse(success=False, error="No sermon notes provided")

    try:
        outline = await extract_sermon_outline_from_text(request.notes)
    except LLMError as exc:
        return ExtractResponse(success=False, error=str(exc))
    except Exception as exc:
        return ExtractResponse(success=False, error=f"Failed to parse notes: {exc}")

    # Fetch commentary candidates for the main passage from each selected source
    candidates: dict[str, ExtractCandidateSource] = {}
    source_map = {
        "mhc": CommentarySource.MHC,
        "calvincommentaries": CommentarySource.CALVIN,
        "scofield": CommentarySource.SCOFIELD,
    }
    for source_key in request.commentaries:
        source = source_map.get(source_key)
        if not source:
            continue
        result = await fetch_commentary_for_reference(outline.main_passage, source)
        if result:
            candidates[source_key] = ExtractCandidateSource(
                source_name=result.source_name,
                entries=[
                    ExtractCandidateEntry(
                        verse_start=e.verse_start,
                        verse_end=e.verse_end,
                        text=e.text,
                    )
                    for e in result.entries
                ],
            )

    return ExtractResponse(
        success=True,
        outline=outline.model_dump(),
        candidates=candidates,
    )
```

**Step 4: Run test — expect pass**

```bash
python -m pytest tests/test_web_extract.py -v
```

Expected: 2 PASSED

**Step 5: Commit**

```bash
git add app/routes/web.py tests/test_web_extract.py
git commit -m "feat: add POST /web/extract endpoint for outline extraction + commentary candidates"
```

---

### Task 5: Modify `POST /web/generate` to use pre-extracted data

**Files:**
- Modify: `app/routes/web.py` (the `generate_sermon_pdf` function)
- Create: `tests/test_web_generate_overrides.py`

**Step 1: Write the failing test**

Create `tests/test_web_generate_overrides.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.models import SermonOutline, SermonMetadata

MOCK_OUTLINE_DICT = SermonOutline(
    metadata=SermonMetadata(title="Test", speaker=None, date=None),
    main_passage="James 3:1",
    points=[],
    all_scripture_refs=[],
).model_dump()


def test_generate_uses_preextracted_outline_skipping_llm():
    """When outline is provided, LLM extraction is not called."""
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
                "outline": MOCK_OUTLINE_DICT,
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
                "outline": MOCK_OUTLINE_DICT,
                "commentary_overrides": [
                    {
                        "source_name": "Matthew Henry",
                        "entries": [{"verse_start": 1, "verse_end": 2, "text": "Test."}]
                    }
                ],
            })

        assert resp.status_code == 200
        # Check generate_sermon_latex was called with commentary_overrides kwarg
        call_kwargs = mock_latex.call_args.kwargs
        assert call_kwargs.get("commentary_overrides") is not None
        assert len(call_kwargs["commentary_overrides"]) == 1
        assert call_kwargs["commentary_overrides"][0].source_name == "Matthew Henry"
```

**Step 2: Run test — expect failure**

```bash
python -m pytest tests/test_web_generate_overrides.py -v
```

Expected: FAIL — generate endpoint ignores `outline` and `commentary_overrides`.

**Step 3: Modify `generate_sermon_pdf` in `app/routes/web.py`**

Replace the extraction block (currently lines ~143–151):

```python
    # Use pre-extracted outline if provided, otherwise extract via LLM
    if request.outline:
        try:
            from ..models import SermonOutline as _SermonOutline
            outline = _SermonOutline(**request.outline)
        except Exception as exc:
            return GenerateResponse(success=False, error=f"Invalid outline data: {exc}")
    else:
        try:
            outline = await extract_sermon_outline_from_text(request.notes)
        except LLMError as exc:
            logger.error("LLM extraction failed: %s", exc)
            return GenerateResponse(success=False, error=str(exc))
        except Exception as exc:
            logger.exception("Unexpected error during extraction")
            return GenerateResponse(success=False, error=f"Failed to parse notes: {exc}")
```

Build `commentary_overrides` from `request.commentary_overrides` (add before the "Generate LaTeX" block):

```python
    # Build pre-selected commentary results if provided
    preloaded_commentary = None
    if request.commentary_overrides:
        from ..commentary import CommentaryResult, CommentarySource, CommentaryEntry
        preloaded_commentary = []
        for item in request.commentary_overrides:
            entries = [
                CommentaryEntry(
                    verse_start=e.verse_start,
                    verse_end=e.verse_end if e.verse_end is not None else e.verse_start,
                    text=e.text,
                )
                for e in item.entries
            ]
            preloaded_commentary.append(CommentaryResult(
                source=CommentarySource.MHC,  # value unused in rendering
                source_name=item.source_name,
                book="", chapter=0, verse=None,
                entries=entries,
            ))
```

Then in the `generate_sermon_latex` call, replace the `commentary_sources` argument:

```python
        latex_content = await generate_sermon_latex(
            outline=outline,
            scripture_version="ESV",
            subpoint_version="NET",
            include_main_passage=True,
            cover_image=cover_image_filename,
            commentary_sources=request.commentaries if not preloaded_commentary else [],
            commentary_overrides=preloaded_commentary,
            include_bulletin=bulletin_data is not None,
            include_prayer_requests=prayer_data is not None
        )
```

**Step 4: Run tests — expect pass**

```bash
python -m pytest tests/test_web_generate_overrides.py -v
```

Expected: 2 PASSED

**Step 5: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

**Step 6: Commit**

```bash
git add app/routes/web.py tests/test_web_generate_overrides.py
git commit -m "feat: use pre-extracted outline and commentary overrides in generate endpoint"
```

---

### Task 6: HTML — three-step wizard structure

Replace the current single form in `app/static/index.html` with the wizard structure.

**Files:**
- Modify: `app/static/index.html`

**Step 1: Replace `<main id="main-content">` contents with the wizard**

The new structure keeps the password modal unchanged. Replace everything inside `<main id="main-content" class="hidden">`:

```html
<main id="main-content" class="hidden">
    <header>
        <h1>Sermon Notes Processor</h1>
        <button id="logout-btn" class="logout-btn">Logout</button>
    </header>

    <!-- Step Indicator -->
    <div class="step-indicator">
        <div class="step active" id="step-ind-1"><span class="step-num">1</span> Input</div>
        <div class="step-connector"></div>
        <div class="step" id="step-ind-2"><span class="step-num">2</span> Review</div>
        <div class="step-connector"></div>
        <div class="step" id="step-ind-3"><span class="step-num">3</span> Done</div>
    </div>

    <!-- Step 1: Input -->
    <div id="step-1">
        <form id="sermon-form">
            <div class="form-group">
                <label for="notes">Sermon Notes</label>
                <textarea id="notes" placeholder="Paste your sermon notes here..." required></textarea>
            </div>

            <div class="form-group">
                <label for="cover-image">Cover Image (optional)</label>
                <div class="file-input-wrapper" id="cover-wrapper">
                    <input type="file" id="cover-image" accept="image/png,image/jpeg,image/webp">
                    <span id="file-name">No file chosen</span>
                </div>
                <div id="image-preview" class="image-preview hidden">
                    <img id="preview-img" alt="Cover preview">
                    <button type="button" id="clear-image" class="clear-btn">Remove</button>
                </div>
            </div>

            <div class="form-group">
                <label>Commentary Sources (optional)</label>
                <div class="checkbox-group">
                    <label class="checkbox-label">
                        <input type="checkbox" id="commentary-mhc" value="mhc">
                        <span>Matthew Henry's Commentary</span>
                    </label>
                    <label class="checkbox-label">
                        <input type="checkbox" id="commentary-calvin" value="calvincommentaries">
                        <span>Calvin's Commentaries</span>
                    </label>
                    <label class="checkbox-label">
                        <input type="checkbox" id="commentary-scofield" value="scofield">
                        <span>Scofield Reference Notes</span>
                    </label>
                </div>
            </div>

            <div class="form-group">
                <label for="bulletin-pdf">Sunday Bulletin (optional PDF)</label>
                <div class="file-input-wrapper" id="bulletin-wrapper">
                    <input type="file" id="bulletin-pdf" accept="application/pdf">
                    <span id="bulletin-file-name">No file chosen</span>
                </div>
                <button type="button" id="clear-bulletin" class="clear-btn hidden">Remove</button>
            </div>

            <div class="form-group">
                <label for="prayer-pdf">Prayer Requests (optional PDF)</label>
                <div class="file-input-wrapper" id="prayer-wrapper">
                    <input type="file" id="prayer-pdf" accept="application/pdf">
                    <span id="prayer-file-name">No file chosen</span>
                </div>
                <button type="button" id="clear-prayer" class="clear-btn hidden">Remove</button>
            </div>

            <button type="submit" id="extract-btn">
                <span id="extract-btn-text">Extract Outline</span>
                <span id="extract-btn-spinner" class="spinner hidden"></span>
            </button>
        </form>

        <div id="extract-error" class="result result-error hidden">
            <h3>Error</h3>
            <p id="extract-error-message"></p>
        </div>
    </div>

    <!-- Step 2: Review -->
    <div id="step-2" class="hidden">
        <div id="outline-summary" class="outline-summary"></div>
        <div id="commentary-cards"></div>
        <div id="review-error" class="result result-error hidden">
            <h3>Error</h3>
            <p id="review-error-message"></p>
        </div>
        <div class="wizard-nav">
            <button type="button" id="back-btn" class="back-btn">← Back</button>
            <button type="button" id="generate-btn">
                <span id="generate-btn-text">Generate PDF</span>
                <span id="generate-btn-spinner" class="spinner hidden"></span>
            </button>
        </div>
    </div>

    <!-- Step 3: Done -->
    <div id="step-3" class="hidden">
        <div class="result result-success">
            <h3>PDF Generated!</h3>
            <div class="download-buttons">
                <a id="download-link" href="#" target="_blank" class="download-btn">Download PDF</a>
                <a id="download-tex-link" href="#" target="_blank" class="download-btn download-btn-secondary">Download TeX</a>
            </div>
        </div>
        <div class="wizard-nav wizard-nav-center">
            <button type="button" id="start-over-btn" class="back-btn">← Start over</button>
        </div>
    </div>
</main>
```

**Step 2: Verify server still loads (no JS changes yet — step 1 visible, steps 2/3 hidden)**

Open http://localhost:8000 and confirm the page loads without console errors. The form should render. Clicking "Extract Outline" does nothing yet (JS wired in next task).

**Step 3: Commit**

```bash
git add app/static/index.html
git commit -m "feat: add three-step wizard HTML structure"
```

---

### Task 7: JS — wizard state machine

Replace `app/static/app.js` entirely with the wizard implementation.

**Files:**
- Modify: `app/static/app.js`

**Step 1: Replace `app/static/app.js` with the following**

```javascript
// ─── State ────────────────────────────────────────────────────────────────────
let coverImageBase64 = null;
let bulletinPdfBase64 = null;
let prayerPdfBase64 = null;
let extractedOutline = null;    // SermonOutline dict from /web/extract
let extractedCandidates = null; // {source_key: {source_name, entries[]}} from /web/extract

// ─── Wizard Navigation ────────────────────────────────────────────────────────
function showStep(n) {
    [1, 2, 3].forEach(i => {
        document.getElementById(`step-${i}`).classList.toggle('hidden', i !== n);
        const ind = document.getElementById(`step-ind-${i}`);
        ind.classList.toggle('active', i === n);
        ind.classList.toggle('done', i < n);
    });
}

// ─── Auth ─────────────────────────────────────────────────────────────────────
const passwordModal = document.getElementById('password-modal');
const mainContent   = document.getElementById('main-content');

async function checkAuth() {
    try {
        const resp = await fetch('/web/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes: '' }),
            credentials: 'include',
        });
        if (resp.status !== 401) { showMainContent(); return; }
    } catch (e) {}
    showPasswordModal();
}

function showPasswordModal() {
    passwordModal.classList.remove('hidden');
    mainContent.classList.add('hidden');
    document.getElementById('password-input').focus();
}

function showMainContent() {
    passwordModal.classList.add('hidden');
    mainContent.classList.remove('hidden');
    showStep(1);
}

document.getElementById('password-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const err = document.getElementById('password-error');
    err.classList.add('hidden');
    try {
        const resp = await fetch('/web/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: document.getElementById('password-input').value }),
            credentials: 'include',
        });
        const data = await resp.json();
        if (data.valid) { showMainContent(); document.getElementById('password-input').value = ''; }
        else { err.classList.remove('hidden'); document.getElementById('password-input').select(); }
    } catch (_) {
        err.textContent = 'Connection error. Please try again.';
        err.classList.remove('hidden');
    }
});

document.getElementById('logout-btn').addEventListener('click', async () => {
    try { await fetch('/web/logout', { method: 'POST', credentials: 'include' }); } catch (_) {}
    coverImageBase64 = bulletinPdfBase64 = prayerPdfBase64 = null;
    extractedOutline = extractedCandidates = null;
    document.getElementById('notes').value = '';
    clearImagePreview();
    clearBulletinPdf();
    clearPrayerPdf();
    document.getElementById('extract-error').classList.add('hidden');
    showPasswordModal();
});

// ─── File helpers ──────────────────────────────────────────────────────────────
function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload  = () => resolve(reader.result.split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

// Cover image
document.getElementById('cover-wrapper').addEventListener('click', () =>
    document.getElementById('cover-image').click());

document.getElementById('cover-image').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) { clearImagePreview(); return; }
    document.getElementById('file-name').textContent = file.name;
    try {
        coverImageBase64 = await readFileAsBase64(file);
        document.getElementById('preview-img').src = URL.createObjectURL(file);
        document.getElementById('image-preview').classList.remove('hidden');
    } catch (_) { clearImagePreview(); }
});

document.getElementById('clear-image').addEventListener('click', clearImagePreview);

function clearImagePreview() {
    document.getElementById('cover-image').value = '';
    document.getElementById('file-name').textContent = 'No file chosen';
    document.getElementById('image-preview').classList.add('hidden');
    document.getElementById('preview-img').src = '';
    coverImageBase64 = null;
}

// Bulletin PDF
document.getElementById('bulletin-wrapper').addEventListener('click', () =>
    document.getElementById('bulletin-pdf').click());

document.getElementById('bulletin-pdf').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) { clearBulletinPdf(); return; }
    document.getElementById('bulletin-file-name').textContent = file.name;
    try {
        bulletinPdfBase64 = await readFileAsBase64(file);
        document.getElementById('clear-bulletin').classList.remove('hidden');
    } catch (_) { clearBulletinPdf(); }
});

document.getElementById('clear-bulletin').addEventListener('click', clearBulletinPdf);

function clearBulletinPdf() {
    document.getElementById('bulletin-pdf').value = '';
    document.getElementById('bulletin-file-name').textContent = 'No file chosen';
    bulletinPdfBase64 = null;
    document.getElementById('clear-bulletin').classList.add('hidden');
}

// Prayer PDF
document.getElementById('prayer-wrapper').addEventListener('click', () =>
    document.getElementById('prayer-pdf').click());

document.getElementById('prayer-pdf').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) { clearPrayerPdf(); return; }
    document.getElementById('prayer-file-name').textContent = file.name;
    try {
        prayerPdfBase64 = await readFileAsBase64(file);
        document.getElementById('clear-prayer').classList.remove('hidden');
    } catch (_) { clearPrayerPdf(); }
});

document.getElementById('clear-prayer').addEventListener('click', clearPrayerPdf);

function clearPrayerPdf() {
    document.getElementById('prayer-pdf').value = '';
    document.getElementById('prayer-file-name').textContent = 'No file chosen';
    prayerPdfBase64 = null;
    document.getElementById('clear-prayer').classList.add('hidden');
}

// ─── Step 1: Extract ──────────────────────────────────────────────────────────
document.getElementById('sermon-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    document.getElementById('extract-error').classList.add('hidden');

    const notes = document.getElementById('notes').value.trim();
    if (!notes) { showExtractError('Please enter sermon notes'); return; }

    const commentaries = ['commentary-mhc', 'commentary-calvin', 'commentary-scofield']
        .map(id => document.getElementById(id))
        .filter(el => el && el.checked)
        .map(el => el.value);

    setExtracting(true);

    try {
        const resp = await fetch('/web/extract', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes, image: coverImageBase64, commentaries }),
            credentials: 'include',
        });

        if (resp.status === 401) { showPasswordModal(); return; }

        const data = await resp.json();

        if (!data.success) { showExtractError(data.error || 'Extraction failed'); return; }

        extractedOutline    = data.outline;
        extractedCandidates = data.candidates;

        renderReviewStep(data.outline, data.candidates);
        showStep(2);

    } catch (_) {
        showExtractError('Connection error. Please try again.');
    } finally {
        setExtracting(false);
    }
});

function setExtracting(loading) {
    document.getElementById('extract-btn').disabled = loading;
    document.getElementById('extract-btn-text').textContent = loading ? 'Extracting…' : 'Extract Outline';
    document.getElementById('extract-btn-spinner').classList.toggle('hidden', !loading);
}

function showExtractError(msg) {
    document.getElementById('extract-error-message').textContent = msg;
    document.getElementById('extract-error').classList.remove('hidden');
}

// ─── Step 2: Review ───────────────────────────────────────────────────────────
function renderReviewStep(outline, candidates) {
    // Outline summary
    const meta = outline.metadata;
    const summaryEl = document.getElementById('outline-summary');
    summaryEl.innerHTML = `
        <h2 class="outline-title">${escapeHtml(meta.title)}</h2>
        <p class="outline-meta">${[meta.speaker, meta.date].filter(Boolean).map(escapeHtml).join(' · ')}</p>
        <p class="outline-passage">Main passage: <strong>${escapeHtml(outline.main_passage)}</strong></p>
    `;

    // Commentary cards
    const cardsEl = document.getElementById('commentary-cards');
    cardsEl.innerHTML = '';

    const sourceKeys = Object.keys(candidates || {});

    if (sourceKeys.length === 0) {
        cardsEl.innerHTML = '<p class="no-commentary">No commentary selected or no results found.</p>';
        return;
    }

    sourceKeys.forEach(sourceKey => {
        const sourceData = candidates[sourceKey];
        const card = document.createElement('div');
        card.className = 'commentary-card';

        let entriesHtml = sourceData.entries.map((entry, i) => {
            const verseLabel = entry.verse_end && entry.verse_end !== entry.verse_start
                ? `vv.${entry.verse_start}–${entry.verse_end}`
                : `v.${entry.verse_start}`;
            const checkId = `entry-${sourceKey}-${i}`;
            const shortText = entry.text.length > 150
                ? entry.text.slice(0, 150) + '…'
                : entry.text;
            const needsExpand = entry.text.length > 150;

            return `
                <label class="commentary-entry">
                    <input type="checkbox" id="${checkId}" data-source-key="${sourceKey}" data-entry-index="${i}" checked>
                    <span class="entry-verse">${escapeHtml(verseLabel)}</span>
                    <span class="entry-text" data-full="${escapeHtml(entry.text)}" data-short="${escapeHtml(shortText)}">
                        ${escapeHtml(shortText)}
                    </span>
                    ${needsExpand ? `<button type="button" class="show-more-btn" data-expanded="false">show more ▾</button>` : ''}
                </label>
            `;
        }).join('');

        card.innerHTML = `
            <div class="card-source-name">${escapeHtml(sourceData.source_name)}</div>
            <div class="card-entries">${entriesHtml}</div>
        `;
        cardsEl.appendChild(card);
    });

    // Wire up show more/less toggles
    cardsEl.querySelectorAll('.show-more-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const expanded = btn.dataset.expanded === 'true';
            const textEl = btn.previousElementSibling;
            textEl.textContent = expanded ? textEl.dataset.short : textEl.dataset.full;
            btn.textContent = expanded ? 'show more ▾' : 'show less ▴';
            btn.dataset.expanded = String(!expanded);
        });
    });
}

// Back to step 1
document.getElementById('back-btn').addEventListener('click', () => {
    document.getElementById('review-error').classList.add('hidden');
    showStep(1);
});

// ─── Step 2 → 3: Generate ─────────────────────────────────────────────────────
document.getElementById('generate-btn').addEventListener('click', async () => {
    document.getElementById('review-error').classList.add('hidden');

    // Collect selected entries grouped by source_name
    const overrideMap = {}; // source_name → {source_name, entries[]}
    const cardsEl = document.getElementById('commentary-cards');

    cardsEl.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        if (!cb.checked) return;
        const sourceKey = cb.dataset.sourceKey;
        const idx = parseInt(cb.dataset.entryIndex, 10);
        const sourceData = extractedCandidates[sourceKey];
        const entry = sourceData.entries[idx];
        const name = sourceData.source_name;
        if (!overrideMap[name]) overrideMap[name] = { source_name: name, entries: [] };
        overrideMap[name].entries.push({
            verse_start: entry.verse_start,
            verse_end: entry.verse_end,
            text: entry.text,
        });
    });

    const commentaryOverrides = Object.values(overrideMap);

    setGenerating(true);

    try {
        const body = {
            notes: document.getElementById('notes').value,
            image: coverImageBase64,
            bulletin_pdf: bulletinPdfBase64,
            prayer_pdf: prayerPdfBase64,
            outline: extractedOutline,
            commentary_overrides: commentaryOverrides,
        };

        const resp = await fetch('/web/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            credentials: 'include',
        });

        if (resp.status === 401) { showPasswordModal(); return; }

        const data = await resp.json();

        if (data.success && data.url) {
            document.getElementById('download-link').href = data.url;
            const texLink = document.getElementById('download-tex-link');
            if (data.tex_url) { texLink.href = data.tex_url; texLink.style.display = 'inline-block'; }
            else { texLink.style.display = 'none'; }
            showStep(3);
        } else {
            document.getElementById('review-error-message').textContent = data.error || 'Unknown error';
            document.getElementById('review-error').classList.remove('hidden');
        }
    } catch (_) {
        document.getElementById('review-error-message').textContent = 'Connection error. Please try again.';
        document.getElementById('review-error').classList.remove('hidden');
    } finally {
        setGenerating(false);
    }
});

function setGenerating(loading) {
    document.getElementById('generate-btn').disabled = loading;
    document.getElementById('generate-btn-text').textContent = loading ? 'Generating…' : 'Generate PDF';
    document.getElementById('generate-btn-spinner').classList.toggle('hidden', !loading);
}

// ─── Step 3: Done ─────────────────────────────────────────────────────────────
document.getElementById('start-over-btn').addEventListener('click', () => {
    extractedOutline = extractedCandidates = null;
    document.getElementById('notes').value = '';
    clearImagePreview(); clearBulletinPdf(); clearPrayerPdf();
    ['commentary-mhc', 'commentary-calvin', 'commentary-scofield'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.checked = false;
    });
    showStep(1);
});

// ─── Utilities ────────────────────────────────────────────────────────────────
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ─── Init ─────────────────────────────────────────────────────────────────────
checkAuth();
```

**Step 2: Verify in browser**

1. Load http://localhost:8000 — step 1 should show.
2. Enter notes, check a commentary source, click "Extract Outline" — spinner shows, then step 2 appears with outline summary and commentary cards.
3. Click "← Back" — returns to step 1.
4. Click "Generate PDF" — spinner, then step 3 with download links.
5. Click "← Start over" — resets to step 1.

**Step 3: Commit**

```bash
git add app/static/app.js
git commit -m "feat: wizard JS — extract, review, generate flow"
```

---

### Task 8: CSS — wizard styles

Add new styles to `app/static/style.css`. Do not remove existing styles.

**Files:**
- Modify: `app/static/style.css` (append to end)

**Step 1: Append the following to the end of `style.css`**

```css
/* ── Step Indicator ─────────────────────────────────────────────────────── */
.step-indicator {
    display: flex;
    align-items: center;
    margin-bottom: 1.5rem;
}

.step {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.875rem;
    font-weight: 600;
    color: #bbb;
    white-space: nowrap;
}

.step.active { color: #800080; }
.step.done   { color: #4caf50; }

.step-num {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 2px solid currentColor;
    font-size: 0.75rem;
}

.step.done .step-num::after { content: '✓'; }
.step.done .step-num { font-size: 0; }
.step.done .step-num::after { font-size: 0.75rem; }

.step-connector {
    flex: 1;
    height: 2px;
    background: #ddd;
    margin: 0 0.5rem;
    min-width: 1rem;
}

/* ── Outline Summary ────────────────────────────────────────────────────── */
.outline-summary {
    background: white;
    border-radius: 8px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
}

.outline-title {
    font-size: 1.25rem;
    color: #800080;
    margin-bottom: 0.25rem;
}

.outline-meta {
    color: #666;
    font-size: 0.875rem;
    margin-bottom: 0.25rem;
}

.outline-passage {
    color: #444;
    font-size: 0.875rem;
}

/* ── Commentary Cards ───────────────────────────────────────────────────── */
.commentary-card {
    background: white;
    border-radius: 8px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
}

.card-source-name {
    font-weight: 700;
    color: #444;
    margin-bottom: 0.75rem;
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.commentary-entry {
    display: grid;
    grid-template-columns: 1.25rem 4rem 1fr auto;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0.5rem 0;
    border-top: 1px solid #f0f0f0;
    cursor: pointer;
    font-weight: normal;
}

.commentary-entry:first-child { border-top: none; }

.commentary-entry input[type="checkbox"] {
    width: 16px;
    height: 16px;
    accent-color: #800080;
    cursor: pointer;
    margin-top: 2px;
}

.entry-verse {
    font-weight: 600;
    color: #800080;
    font-size: 0.8rem;
    white-space: nowrap;
}

.entry-text {
    color: #555;
    font-size: 0.875rem;
    line-height: 1.45;
}

.show-more-btn {
    background: none;
    border: none;
    color: #800080;
    font-size: 0.75rem;
    cursor: pointer;
    padding: 0;
    white-space: nowrap;
}

.show-more-btn:hover { text-decoration: underline; }

.no-commentary {
    color: #888;
    font-size: 0.875rem;
    padding: 1rem 0;
    text-align: center;
}

/* ── Wizard Navigation ──────────────────────────────────────────────────── */
.wizard-nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 1.5rem;
}

.wizard-nav-center {
    justify-content: center;
}

.back-btn {
    padding: 0.75rem 1.25rem;
    font-size: 0.9rem;
    background: transparent;
    color: #666;
    border: 1px solid #ccc;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s;
}

.back-btn:hover {
    background: #f0f0f0;
    border-color: #999;
}

#generate-btn {
    padding: 0.9rem 2rem;
    font-size: 1rem;
    font-weight: 600;
    background: #800080;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    transition: background 0.2s;
}

#generate-btn:hover:not(:disabled) { background: #600060; }
#generate-btn:disabled { background: #999; cursor: not-allowed; }
```

**Step 2: Verify visually in browser**

Load http://localhost:8000 and confirm:
- Step indicator shows "1 Input · · · 2 Review · · · 3 Done"
- After extraction, step 2 shows outline summary card and commentary cards with checkboxes
- Show more/less toggles work
- Active step is purple, done steps are green with a checkmark

**Step 3: Commit**

```bash
git add app/static/style.css
git commit -m "feat: wizard CSS — step indicator, commentary cards, navigation"
```

---

### Task 9: Final verification and cleanup

**Step 1: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

**Step 2: End-to-end smoke test**

1. Open http://localhost:8000
2. Paste sermon notes, check Matthew Henry, click "Extract Outline"
3. Verify step 2 shows outline summary + MHC commentary entries
4. Uncheck one entry, click "Generate PDF"
5. Verify PDF downloads and excluded entry is not in the commentary appendix
6. Click "← Start over", verify form resets

**Step 3: Commit design doc update**

```bash
git add docs/plans/2026-02-21-commentary-wizard-design.md
git commit -m "docs: mark commentary wizard design as fully implemented"
```
