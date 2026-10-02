import base64
import json
import logging

import httpx

from .anthropic_config import (
    ANTHROPIC_API_VERSION,
    ANTHROPIC_FALLBACK_BETA,
    ANTHROPIC_FALLBACKS,
    ANTHROPIC_MESSAGES_URL,
    ANTHROPIC_MODEL,
    AnthropicRefusal,
    raise_if_refused,
)
from .config import get_settings
from .models import SermonOutline

logger = logging.getLogger(__name__)

SERMON_EXTRACTION_PROMPT_BASE = '''You are analyzing sermon notes. Extract the structured content into JSON format.

Analyze the document and extract:
1. **Metadata**: title, speaker name, date, series name (if present)
2. **Main Scripture Passage**: The primary passage for the sermon (e.g., "Ephesians 4:22-25")
3. **Foundational Principle**: Any key principle, thesis, or summary statement (if present)
4. **Outline Structure**:
   - Numbered main points (1, 2, 3...)
   - Lettered sub-points (A, B, C...) under each main point
   - Bullets (marked with ●, -, or •) under sub-points
5. **Scripture References**: All Bible references mentioned in parentheses
6. **Tables**: Any pipe-delimited tables (lines starting/containing | with multiple columns)

CRITICAL STRUCTURE RULES:
- Create sub-points when items are EXPLICITLY marked with letters (A, B, C) OR numbers (1, 2, 3) under a section heading
- When numbered items (1, 2, 3...) appear under a heading WITH scripture references in parentheses, use sub_points with label "1", "2", "3" etc. and extract each item's scripture refs into that sub_point's scripture_refs
- Only create bullets when EXPLICITLY marked with ●, -, or • in the original
- Keep related sentences together as "content" - do NOT split prose into separate bullets
- If a section is just a numbered list (1, 2, 3...) at the TOP level without a parent heading, each item is a separate main point
- Sections that appear twice (brief then expanded) should be treated as SEPARATE main points
- Preserve the EXACT structure from the original notes

For scripture references:
- Extract ALL parenthetical references like (Prov. 6:16, 12:22) into scripture_refs array
- Use standard format: "Book Chapter:Verse" or "Book Chapter:Verse-Verse"
- Include book numbers: "1 John 3:16" not "I John 3:16"
- Keep the parenthetical reference in the content text as well
- IMPORTANT: When a main point title ends with a parenthetical verse range like "(vv 11-12)", "(13-15)", "(v. 3)", "(v.3)", or "(v 3)", extract that range into the point's scripture_refs as the fully-qualified reference (e.g., "Titus 2:11-12" or "Titus 3:3"). This applies to both single verses (v. N) and ranges (vv N-N). This signals that the point covers those verses and scripture will be displayed alongside it.

For scripture_verse matching (sub-points to main passage):
- The main_passage defines the passage being preached (e.g., "Ephesians 4:22-25")
- Each sub-point typically addresses a specific verse or verse range within that passage
- Read the content/title of each sub-point carefully and identify which verse of the main passage it discusses
- Set scripture_verse to the fully-qualified verse reference including book name and chapter (e.g., "Ephesians 4:22" not just "22", "v. 22", "vv. 22-23", or "4:22")
- If a sub-point spans multiple consecutive verses, use a range: "Ephesians 4:22-23"
- If you cannot determine which verse a sub-point addresses, leave scripture_verse as null
- Do NOT put parenthetical cross-references into scripture_verse — those belong in scripture_refs only
- SAME RULE FOR POINTS WITH NO SUB-POINTS: if a point title ends with "(vv N-N)" or "(v. N)" or "(v N)", put the fully-qualified ref in that point's scripture_refs
- NEVER output partial forms like "v. 4", "vv. 1-3", or "3:4" in scripture_verse — always "Book Chapter:Verse" format

LAYOUT HINTS (for rendering):
- Sub-points WITH scripture_verse OR scripture_refs will show scripture on left, notes on right (two-column)
- Sub-points WITHOUT scripture_verse AND without scripture_refs will be full-width text
- Each sub-point gets its own page (whether labeled A/B/C or 1/2/3)
- Points with simple bullets (●, -, •) but NO sub-points go on ONE page
- Tables will be rendered as formatted tables in the output
- IMPORTANT: Tables should be placed INSIDE the point where they appear in the notes, using that point's "tables" field. Only use the top-level "tables" if a table is not associated with any specific point.

TABLE FORMAT:
- Tables are marked with pipe characters (|) separating columns
- First row with pipes is the header row
- Example:
  | Greek | Transliteration | Meaning |
  | λόγος | logos | word |
  | ἀγάπη | agape | love |
- Extract each table into the "tables" array with headers and rows
- Tables may have an optional caption/title on the line before them

STANDALONE STATEMENTS:
- Notes often set a sentence apart on its own line (centered, indented, italic, or in quotation marks) instead of making it part of a point. These are NOT bullets, NOT numbered items, and NOT part of a neighboring sentence.
- foundational_principle holds ONLY the main idea / thesis text itself. Never append a following quote or statement to it.
- A standalone quote or statement directly under the main idea, before the first point → "key_quotes" (keep its quotation marks if it has them).
- A standalone summary or transition statement that comes after a section's items (after its sub-points, list, or questions) → that point's "closing_statement". The final summary statement at the end of the notes is the last point's closing_statement.
- A point's "content" is only the text right after its heading, before its sub-points or list. A statement that comes AFTER the sub-points is the closing_statement, not content.

IMPORTANT STRUCTURE RULES:
- Use "bullets" at the POINT level for simple bullet lists (●, -, •) WITHOUT sub-points
- Use "sub_points" when items are lettered (A, B, C) OR numbered (1, 2, 3) under a section heading — use the original label ("A" or "1") as the label field
- IMPORTANT: When numbered items appear UNDER A HEADING and have parenthetical scripture references, ALWAYS use sub_points so each item gets its own page with scripture displayed alongside it. Exception: if the numbered items ARE the top-level structure with no parent heading, they are separate main points (not sub_points).
- Points with just prose content use "content" field
- Numbered items WITHOUT scripture references and WITHOUT a parent heading use "numbered_items"

Return ONLY valid JSON matching this exact structure:
{
  "metadata": {
    "title": "string",
    "speaker": "string or null",
    "date": "string or null",
    "series": "string or null",
    "map": "one of: paul-journeys, paul-journeys-biblica, jerusalem, galilee, palestine-conquest, palestine-overview — or null if none fits. Choose based on the primary passage: Pauline epistles/Acts → paul-journeys; Jerusalem/Temple passages → jerusalem; Galilee/Gospel narratives → galilee; Joshua/Judges/conquest → palestine-conquest; general OT/Holy Land → palestine-overview."
  },
  "main_passage": "string (e.g., 'James 3:1-12')",
  "foundational_principle": "string or null",
  "foundational_scripture": "string or null (ONLY a reference the notes explicitly attach to the foundational principle; null if none — never copy main_passage here)",
  "key_quotes": ["standalone quote under the main idea"],
  "points": [
    {
      "number": 1,
      "title": "string",
      "content": "string or null (prose content for the point)",
      "bullets": ["simple bullet without letter", "another bullet"],
      "numbered_items": ["First numbered item with explanation", "Second numbered item"],
      "sub_points": [
        {
          "label": "A or 1 (use original label from notes)",
          "title": "string or null",
          "content": "string (the title/theme description after the label)",
          "bullets": ["first bullet point", "second bullet point"],
          "scripture_verse": "specific verse(s) from main passage for this sub-point (e.g., 'James 3:2')",
          "scripture_refs": ["scripture references mentioned in THIS specific sub-point only"]
        }
      ],
      "scripture_refs": ["array of scripture references for this point"],
      "tables": [
        {
          "headers": ["Column 1", "Column 2", "Column 3"],
          "rows": [["cell1", "cell2", "cell3"], ["cell4", "cell5", "cell6"]],
          "caption": "optional table title or null"
        }
      ],
      "closing_statement": "string or null (standalone statement after this point's items)"
    }
  ],
  "tables": [],
  "all_scripture_refs": ["array of ALL unique scripture references in the document"]
}'''


PDF_LAYOUT_GUIDANCE = '''PDF LAYOUT NOTES (this input is a PDF, not pasted text):
- Pages may use two or more text columns. Read each column top to bottom before moving to the next column, and keep content that continues across a column or page break together in the right point.
- Tables in a PDF are visual grids or aligned columns, NOT pipe-delimited text. Treat any grid, chart, or side-by-side comparison (e.g., "Pride" vs "Humility" columns) as a table: headers are the column titles, and each visual row is one row. Cells that wrap onto several lines are ONE cell — join the wrapped lines with a space.
- Keep every row and cell of a table in its original order; do not summarize, drop, or merge rows.
- Put a table in the "tables" field of the point it belongs to (the point it appears under or directly illustrates). If it stands alone (e.g., on its own page with no heading tying it to a point), put it in the top-level "tables" array.
- Ordinary numbered or lettered lists and question lists are NOT tables, even when they are aligned.
- Ignore page headers/footers, page numbers, and blank fill-in lines.'''


class LLMError(Exception):
    """Raised when LLM API call fails."""
    def __init__(self, message: str, status_code: int = 500):
        self.status_code = status_code
        super().__init__(message)


async def _normalize_scripture_refs(outline: SermonOutline) -> SermonOutline:
    """Use Fable to qualify partial verse refs (e.g. 'v. 4' → 'Titus 3:4').

    Collects all scripture_verse / scripture_refs fields, sends them to Claude
    with the main passage for context, patches corrections back into the outline.
    Silently returns the original outline if anything goes wrong.
    """
    if not outline.main_passage:
        return outline

    # Collect every ref with a stable ID
    refs: list[dict] = []
    for pi, point in enumerate(outline.points):
        for ri, ref in enumerate(point.scripture_refs or []):
            refs.append({"id": f"p{pi}.r{ri}", "ref": ref})
        for si, sub in enumerate(point.sub_points or []):
            if sub.scripture_verse:
                refs.append({"id": f"p{pi}.s{si}.v", "ref": sub.scripture_verse})
            for ri, ref in enumerate(sub.scripture_refs or []):
                refs.append({"id": f"p{pi}.s{si}.r{ri}", "ref": ref})

    if not refs:
        return outline

    settings = get_settings()
    if not settings.anthropic_api_key:
        return outline

    prompt = (
        f'Main passage: "{outline.main_passage}"\n\n'
        "Some of the scripture references below may be partial (e.g. \"v. 4\", "
        "\"vv. 1-3\", \"3:4\"). Using the book and chapter from the main passage, "
        "qualify any partial refs. Leave already fully-qualified refs unchanged.\n\n"
        "Return ONLY a JSON object mapping each id to its corrected ref. "
        "Only include entries that needed correction.\n\n"
        f"Refs:\n{json.dumps(refs)}"
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                ANTHROPIC_MESSAGES_URL,
                json={
                    "model": ANTHROPIC_MODEL,
                    "fallbacks": ANTHROPIC_FALLBACKS,
                    "max_tokens": 4096,
                    "output_config": {"effort": "low"},
                    "messages": [{"role": "user", "content": prompt}],
                },
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "content-type": "application/json",
                    "anthropic-version": ANTHROPIC_API_VERSION,
                    "anthropic-beta": ANTHROPIC_FALLBACK_BETA,
                },
                timeout=60.0,
            )
            response.raise_for_status()

        data = response.json()
        raise_if_refused(data)
        text = "".join(
            block.get("text", "") for block in data.get("content", [])
            if block.get("type") == "text"
        ).strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:-1])
        corrections: dict[str, str] = json.loads(text)

        if not corrections:
            return outline

        d = outline.model_dump()
        for pi, point in enumerate(d["points"]):
            for ri in range(len(point.get("scripture_refs") or [])):
                key = f"p{pi}.r{ri}"
                if key in corrections:
                    d["points"][pi]["scripture_refs"][ri] = corrections[key]
            for si, sub in enumerate(point.get("sub_points") or []):
                if f"p{pi}.s{si}.v" in corrections:
                    d["points"][pi]["sub_points"][si]["scripture_verse"] = corrections[f"p{pi}.s{si}.v"]
                for ri in range(len(sub.get("scripture_refs") or [])):
                    key = f"p{pi}.s{si}.r{ri}"
                    if key in corrections:
                        d["points"][pi]["sub_points"][si]["scripture_refs"][ri] = corrections[key]
        return SermonOutline(**d)

    except Exception as exc:
        logger.warning("Scripture ref normalization failed (using original): %s", exc)
        return outline


async def _assign_missing_verse_refs(outline: SermonOutline) -> SermonOutline:
    """Use Fable to infer main-passage verse refs for points/sub-points that have none.

    Only fills in items with no existing ref — does not overwrite anything.
    """
    if not outline.main_passage:
        return outline

    items: list[dict] = []
    for pi, point in enumerate(outline.points):
        if not point.scripture_refs:
            text = (point.title or point.content or "").strip()[:400]
            if text:
                items.append({"id": f"p{pi}", "text": text})
        for si, sub in enumerate(point.sub_points or []):
            if not sub.scripture_verse:
                text = ((sub.title or "") + " " + (sub.content or "")).strip()[:400]
                if text:
                    items.append({"id": f"p{pi}.s{si}", "text": text})

    if not items:
        return outline

    settings = get_settings()
    if not settings.anthropic_api_key:
        return outline

    prompt = (
        f'Main passage: "{outline.main_passage}"\n\n'
        "Below are sermon items with no verse assignment. For each, if it clearly "
        "addresses a specific verse or verse range within the main passage, return "
        "the fully-qualified ref (e.g. \"Titus 3:4\" or \"Titus 3:4-5\"). "
        "If the item is thematic or maps to no single verse, return null.\n\n"
        "Return ONLY a JSON object: {\"<id>\": \"ref or null\", ...}. Include every id.\n\n"
        f"{json.dumps(items, ensure_ascii=False)}"
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                ANTHROPIC_MESSAGES_URL,
                json={
                    "model": ANTHROPIC_MODEL,
                    "fallbacks": ANTHROPIC_FALLBACKS,
                    "max_tokens": 4096,
                    "output_config": {"effort": "low"},
                    "messages": [{"role": "user", "content": prompt}],
                },
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "content-type": "application/json",
                    "anthropic-version": ANTHROPIC_API_VERSION,
                    "anthropic-beta": ANTHROPIC_FALLBACK_BETA,
                },
                timeout=60.0,
            )
            response.raise_for_status()

        data = response.json()
        raise_if_refused(data)
        text = "".join(
            block.get("text", "") for block in data.get("content", [])
            if block.get("type") == "text"
        ).strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:-1])
        assignments: dict = json.loads(text)

        if not assignments:
            return outline

        d = outline.model_dump()
        for pi, point in enumerate(d["points"]):
            key = f"p{pi}"
            if assignments.get(key):
                refs = d["points"][pi].setdefault("scripture_refs", [])
                if assignments[key] not in refs:
                    refs.append(assignments[key])
            for si in range(len(point.get("sub_points") or [])):
                key = f"p{pi}.s{si}"
                if assignments.get(key):
                    d["points"][pi]["sub_points"][si]["scripture_verse"] = assignments[key]
        return SermonOutline(**d)

    except Exception as exc:
        logger.warning("Verse ref assignment failed (using original): %s", exc)
        return outline


def _pdf_prompt(notes: str | None) -> str:
    """Build the extraction prompt for a PDF, with optional pasted notes as context."""
    parts = [SERMON_EXTRACTION_PROMPT_BASE, PDF_LAYOUT_GUIDANCE]
    if notes and notes.strip():
        parts.append(
            "SUPPLEMENTARY NOTES: The pastor also pasted the text below. The PDF is the "
            "primary source for structure and tables; use these notes only to fill in or "
            f"clarify content.\n\n{notes.strip()}"
        )
    return "\n\n".join(parts)


async def extract_sermon_outline(pdf_bytes: bytes, notes: str | None = None) -> SermonOutline:
    """
    Use Claude API to extract structured sermon outline from PDF.

    Args:
        pdf_bytes: Raw PDF file bytes
        notes: Optional pasted notes to use as supplementary context

    Returns:
        SermonOutline with extracted content

    Raises:
        LLMError: If API call fails or response is invalid
    """
    settings = get_settings()
    api_key = settings.anthropic_api_key

    if not api_key:
        raise LLMError(
            "Anthropic API key not configured. Set ANTHROPIC_API_KEY.",
            status_code=503
        )

    # Encode PDF as base64 for Claude's document capability
    pdf_base64 = base64.b64encode(pdf_bytes).decode()

    # Build the API request
    request_body = {
        "model": ANTHROPIC_MODEL,
        "fallbacks": ANTHROPIC_FALLBACKS,
        "max_tokens": 16384,
        "output_config": {"effort": "medium"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": _pdf_prompt(notes)
                    }
                ]
            }
        ]
    }

    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": ANTHROPIC_API_VERSION,
        "anthropic-beta": ANTHROPIC_FALLBACK_BETA
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                ANTHROPIC_MESSAGES_URL,
                json=request_body,
                headers=headers,
                timeout=120.0
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        detail = f"Anthropic API request failed with status {status}."

        if status == 401:
            detail = "Anthropic API key is invalid. Check ANTHROPIC_API_KEY."
        elif status == 429:
            detail = "Anthropic API rate limit exceeded. Try again later."

        logger.warning("Anthropic API returned %s", status)
        raise LLMError(detail, status_code=502) from exc
    except httpx.RequestError as exc:
        logger.error("Error connecting to Anthropic API: %s", exc)
        raise LLMError(
            "Could not reach the Anthropic API. Try again later.",
            status_code=502
        ) from exc

    # Parse the response
    data = response.json()
    try:
        raise_if_refused(data)
    except AnthropicRefusal as exc:
        logger.warning("Claude declined sermon extraction (category: %s)", exc)
        raise LLMError(
            "Claude declined to process these sermon notes, and the fallback model "
            "declined too. Try again, or simplify the notes and retry.",
            status_code=422,
        ) from exc
    content_blocks = data.get("content", [])

    if not content_blocks:
        raise LLMError("No content returned from Claude API.")

    # Extract text from response
    text_content = ""
    for block in content_blocks:
        if block.get("type") == "text":
            text_content += block.get("text", "")

    # Parse JSON from response
    try:
        # Handle potential markdown code blocks
        json_text = text_content.strip()
        if json_text.startswith("```"):
            lines = json_text.split("\n")
            # Remove first line (```json) and last line (```)
            json_text = "\n".join(lines[1:-1])

        outline_data = json.loads(json_text)
        outline = SermonOutline(**outline_data)
        outline = await _normalize_scripture_refs(outline)
        return await _assign_missing_verse_refs(outline)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Claude response as JSON: %s", text_content[:500])
        raise LLMError(
            "Failed to parse sermon structure from AI response.",
            status_code=500
        ) from exc
    except Exception as exc:
        logger.exception("Failed to validate sermon outline")
        raise LLMError(
            f"Invalid sermon outline structure: {exc}",
            status_code=500
        ) from exc


async def extract_sermon_outline_from_text(text: str) -> SermonOutline:
    """
    Use Claude API to extract structured sermon outline from plain text.

    Args:
        text: Plain text sermon notes

    Returns:
        SermonOutline with extracted content

    Raises:
        LLMError: If API call fails or response is invalid
    """
    settings = get_settings()
    api_key = settings.anthropic_api_key

    if not api_key:
        raise LLMError(
            "Anthropic API key not configured. Set ANTHROPIC_API_KEY.",
            status_code=503
        )

    # Build the API request with text content
    request_body = {
        "model": ANTHROPIC_MODEL,
        "fallbacks": ANTHROPIC_FALLBACKS,
        "max_tokens": 8192,
        "output_config": {"effort": "medium"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Here are the sermon notes to analyze:\n\n{text}\n\n{SERMON_EXTRACTION_PROMPT_BASE}"
                    }
                ]
            }
        ]
    }

    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": ANTHROPIC_API_VERSION,
        "anthropic-beta": ANTHROPIC_FALLBACK_BETA
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                ANTHROPIC_MESSAGES_URL,
                json=request_body,
                headers=headers,
                timeout=120.0
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        detail = f"Anthropic API request failed with status {status}."

        if status == 401:
            detail = "Anthropic API key is invalid. Check ANTHROPIC_API_KEY."
        elif status == 429:
            detail = "Anthropic API rate limit exceeded. Try again later."

        logger.warning("Anthropic API returned %s", status)
        raise LLMError(detail, status_code=502) from exc
    except httpx.RequestError as exc:
        logger.error("Error connecting to Anthropic API: %s", exc)
        raise LLMError(
            "Could not reach the Anthropic API. Try again later.",
            status_code=502
        ) from exc

    # Parse the response
    data = response.json()
    try:
        raise_if_refused(data)
    except AnthropicRefusal as exc:
        logger.warning("Claude declined sermon extraction (category: %s)", exc)
        raise LLMError(
            "Claude declined to process these sermon notes, and the fallback model "
            "declined too. Try again, or simplify the notes and retry.",
            status_code=422,
        ) from exc
    content_blocks = data.get("content", [])

    if not content_blocks:
        raise LLMError("No content returned from Claude API.")

    # Extract text from response
    text_content = ""
    for block in content_blocks:
        if block.get("type") == "text":
            text_content += block.get("text", "")

    # Parse JSON from response
    try:
        # Handle potential markdown code blocks
        json_text = text_content.strip()
        if json_text.startswith("```"):
            lines = json_text.split("\n")
            # Remove first line (```json) and last line (```)
            json_text = "\n".join(lines[1:-1])

        outline_data = json.loads(json_text)
        outline = SermonOutline(**outline_data)
        outline = await _normalize_scripture_refs(outline)
        return await _assign_missing_verse_refs(outline)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Claude response as JSON: %s", text_content[:500])
        raise LLMError(
            "Failed to parse sermon structure from AI response.",
            status_code=500
        ) from exc
    except Exception as exc:
        logger.exception("Failed to validate sermon outline")
        raise LLMError(
            f"Invalid sermon outline structure: {exc}",
            status_code=500
        ) from exc
