import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable

import httpx

from .config import get_settings

logger = logging.getLogger(__name__)


def extract_strongs_numbers(html_text: str) -> set[str]:
    """Extract Strong's numbers from NET Bible HTML response.

    The NET API returns HTML with Strong's numbers in data-num attributes:
    <st data-num="659" class="">lay aside</st>

    Returns set of Strong's numbers as strings (e.g., {'659', '444', '225'})
    """
    pattern = r'data-num="(\d+)"'
    matches = re.findall(pattern, html_text)
    return set(matches)


class ScriptureVersion(str, Enum):
    ESV = "ESV"
    NET = "NET"


@dataclass
class ScriptureLookupOptions:
    include_headings: bool = False
    include_verse_numbers: bool = False
    include_footnotes: bool = False
    include_short_copyright: bool = True


@dataclass
class ScriptureLookupResult:
    reference: str
    version: ScriptureVersion
    text: str
    canonical: str | None = None
    translation_name: str | None = None
    strongs_numbers: set[str] = field(default_factory=set)


class ScriptureLookupError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.status_code = status_code
        super().__init__(message)


def _bool_param(value: bool) -> str:
    return "true" if value else "false"


async def fetch_scripture(
    reference: str,
    version: ScriptureVersion,
    options: ScriptureLookupOptions | None = None
) -> ScriptureLookupResult:
    if not reference or not reference.strip():
        raise ScriptureLookupError("Scripture reference is required.", status_code=400)

    opts = options or ScriptureLookupOptions()
    handler = _VERSION_HANDLERS.get(version)

    if not handler:
        raise ScriptureLookupError(
            f"Unsupported scripture version '{version}'.",
            status_code=400
        )

    return await handler(reference.strip(), opts)


async def _fetch_esv(
    reference: str,
    options: ScriptureLookupOptions
) -> ScriptureLookupResult:
    settings = get_settings()
    api_key = (settings.esv_api_key or os.getenv("ESV_API_KEY", "")).strip()

    if not api_key:
        raise ScriptureLookupError(
            "ESV API key is not configured. Set ESV_API_KEY.",
            status_code=503
        )

    auth_header = api_key if api_key.startswith("Token ") else f"Token {api_key}"

    params = {
        "q": reference,
        "include-passage-references": "false",
        "include-verse-numbers": "true",
        "include-first-verse-numbers": "true",
        "include-footnotes": _bool_param(options.include_footnotes),
        "include-footnote-body": _bool_param(options.include_footnotes),
        "include-headings": _bool_param(options.include_headings),
        "include-short-copyright": _bool_param(options.include_short_copyright),
    }

    headers = {"Authorization": f"Token {settings.esv_api_key}"}
    headers = {"Authorization": auth_header}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.esv.org/v3/passage/text/",
                params=params,
                headers=headers,
                timeout=15.0
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        detail = f"ESV API request failed with status {status}."

        if status in (401, 403):
            detail = "ESV API key was rejected. Check ESV_API_KEY."

        logger.warning(
            "ESV API returned %s for reference '%s'",
            status,
            reference
        )
        raise ScriptureLookupError(
            detail,
            status_code=502
        ) from exc
    except httpx.RequestError as exc:
        logger.error("Error connecting to ESV API: %s", exc)
        raise ScriptureLookupError(
            "Could not reach the ESV API. Try again later.",
            status_code=502
        ) from exc

    data = response.json()
    passages = data.get("passages") or []

    if not passages:
        raise ScriptureLookupError(
            "No passage text returned for the given reference.",
            status_code=404
        )

    text = "\n\n".join(passage.strip() for passage in passages if passage.strip())

    return ScriptureLookupResult(
        reference=reference,
        version=ScriptureVersion.ESV,
        canonical=data.get("canonical"),
        text=text,
        translation_name="English Standard Version"
    )


async def _fetch_net(
    reference: str,
    options: ScriptureLookupOptions
) -> ScriptureLookupResult:
    """Fetch scripture from the NET Bible API (free, no key required)."""
    params = {
        "passage": reference,
        "type": "text",
        "formatting": "full",  # Include Strong's numbers
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://labs.bible.org/api/",
                params=params,
                timeout=15.0
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        logger.warning(
            "NET API returned %s for reference '%s'",
            status,
            reference
        )
        raise ScriptureLookupError(
            f"NET API request failed with status {status}.",
            status_code=502
        ) from exc
    except httpx.RequestError as exc:
        logger.error("Error connecting to NET API: %s", exc)
        raise ScriptureLookupError(
            "Could not reach the NET Bible API. Try again later.",
            status_code=502
        ) from exc

    text = response.text.strip()

    if not text or "passage not found" in text.lower():
        raise ScriptureLookupError(
            "No passage text returned for the given reference.",
            status_code=404
        )

    # Extract Strong's numbers from the HTML response
    strongs = extract_strongs_numbers(text)

    return ScriptureLookupResult(
        reference=reference,
        version=ScriptureVersion.NET,
        canonical=None,
        text=text,
        translation_name="New English Translation",
        strongs_numbers=strongs
    )


VERSION_HANDLER = Callable[[str, ScriptureLookupOptions], Awaitable[ScriptureLookupResult]]

_VERSION_HANDLERS: dict[ScriptureVersion, VERSION_HANDLER] = {
    ScriptureVersion.ESV: _fetch_esv,
    ScriptureVersion.NET: _fetch_net,
}
