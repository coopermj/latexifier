import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..auth import RequireAPIKey
from ..scripture import (
    ScriptureLookupError,
    ScriptureLookupOptions,
    ScriptureVersion,
    fetch_scripture,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scripture", tags=["scripture"])


class ScriptureResponse(BaseModel):
    reference: str
    canonical: str | None = None
    text: str
    version: ScriptureVersion
    translation: str | None = None


@router.get(
    "",
    response_model=ScriptureResponse,
    summary="Lookup a scripture passage",
    description="Fetch scripture text for the given reference and version."
)
async def lookup_scripture(
    _: RequireAPIKey,
    reference: str = Query(
        ...,
        alias="q",
        description="Passage reference (e.g., 'John 3:16-18')"
    ),
    version: ScriptureVersion = Query(
        ScriptureVersion.ESV,
        description="Bible version/translation to use"
    ),
    include_headings: bool = Query(
        False,
        description="Include section headings when supported"
    ),
    include_verse_numbers: bool = Query(
        False,
        description="Include verse numbers when supported"
    ),
    include_footnotes: bool = Query(
        False,
        description="Include footnotes when supported"
    ),
    include_short_copyright: bool = Query(
        True,
        description="Include short copyright notice when supported"
    ),
):
    options = ScriptureLookupOptions(
        include_headings=include_headings,
        include_verse_numbers=include_verse_numbers,
        include_footnotes=include_footnotes,
        include_short_copyright=include_short_copyright,
    )

    try:
        result = await fetch_scripture(reference, version, options)
    except ScriptureLookupError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except Exception:
        logger.exception("Unexpected error while fetching scripture")
        raise HTTPException(
            status_code=500,
            detail="Unable to fetch scripture at this time."
        )

    return ScriptureResponse(
        reference=result.reference,
        canonical=result.canonical,
        text=result.text,
        version=result.version,
        translation=result.translation_name,
    )
