import base64
import json
import logging

import httpx

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

LAYOUT HINTS (for rendering):
- Sub-points WITH scripture_refs will show scripture on left, notes on right (two-column)
- Sub-points WITHOUT scripture_refs will be full-width text
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

IMPORTANT STRUCTURE RULES:
- Use "bullets" at the POINT level for simple bullet lists (●, -, •) WITHOUT sub-points
- Use "sub_points" when items are lettered (A, B, C) OR numbered (1, 2, 3) under a section heading — use the original label ("A" or "1") as the label field
- IMPORTANT: When numbered items have parenthetical scripture references, ALWAYS use sub_points so each item gets its own page with scripture displayed alongside it
- Points with just prose content use "content" field
- Numbered items WITHOUT scripture references and WITHOUT a parent heading use "numbered_items"

Return ONLY valid JSON matching this exact structure:
{
  "metadata": {
    "title": "string",
    "speaker": "string or null",
    "date": "string or null",
    "series": "string or null"
  },
  "main_passage": "string (e.g., 'James 3:1-12')",
  "foundational_principle": "string or null",
  "foundational_scripture": "string or null (scripture ref for foundational principle)",
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
      ]
    }
  ],
  "tables": [],
  "all_scripture_refs": ["array of ALL unique scripture references in the document"]
}'''


class LLMError(Exception):
    """Raised when LLM API call fails."""
    def __init__(self, message: str, status_code: int = 500):
        self.status_code = status_code
        super().__init__(message)


async def extract_sermon_outline(pdf_bytes: bytes) -> SermonOutline:
    """
    Use Claude API to extract structured sermon outline from PDF.

    Args:
        pdf_bytes: Raw PDF file bytes

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
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
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
                        "text": SERMON_EXTRACTION_PROMPT
                    }
                ]
            }
        ]
    }

    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=request_body,
                headers=headers,
                timeout=60.0
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
        return SermonOutline(**outline_data)
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
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
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
        "anthropic-version": "2023-06-01"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=request_body,
                headers=headers,
                timeout=60.0
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
        return SermonOutline(**outline_data)
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
