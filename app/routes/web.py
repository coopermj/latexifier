"""Web interface routes for sermon notes processing."""
import base64
import hashlib
import json
import logging
import secrets
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Cookie, Response
from pydantic import BaseModel

from ..commentary import CommentarySource, fetch_commentary_for_reference
from ..compiler import CompilationError
from ..config import get_settings
from ..llm import extract_sermon_outline_from_text, LLMError
from ..models import SermonOutline
from ..sermon_latex import generate_sermon_latex
from ..storage import save_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/web", tags=["web"])


def _get_sessions_file() -> Path:
    """Get path to sessions file."""
    settings = get_settings()
    return Path(settings.storage_path) / ".sessions.json"


def _load_sessions() -> set[str]:
    """Load sessions from file."""
    sessions_file = _get_sessions_file()
    if sessions_file.exists():
        try:
            data = json.loads(sessions_file.read_text())
            return set(data.get("sessions", []))
        except Exception:
            pass
    return set()


def _save_sessions(sessions: set[str]) -> None:
    """Save sessions to file."""
    sessions_file = _get_sessions_file()
    sessions_file.parent.mkdir(parents=True, exist_ok=True)
    sessions_file.write_text(json.dumps({"sessions": list(sessions)}))


# Load sessions from file on startup
_valid_sessions: set[str] = _load_sessions()


class AuthRequest(BaseModel):
    password: str


class AuthResponse(BaseModel):
    valid: bool


class CommentaryEntryModel(BaseModel):
    verse_start: int
    verse_end: int | None = None
    text: str


class CommentarySourceModel(BaseModel):
    source_name: str
    entries: list[CommentaryEntryModel]


# Aliases for semantic clarity in each context
ExtractCandidateEntry = CommentaryEntryModel
ExtractCandidateSource = CommentarySourceModel


class ExtractRequest(BaseModel):
    notes: str
    image: str | None = None
    commentaries: list[str] = []


class ExtractResponse(BaseModel):
    success: bool
    outline: SermonOutline | None = None
    candidates: dict[str, ExtractCandidateSource] = {}
    error: str | None = None


# Aliases for semantic clarity in each context
SelectedCommentaryEntry = CommentaryEntryModel
SelectedCommentaryResult = CommentarySourceModel


class GenerateRequest(BaseModel):
    notes: str
    image: str | None = None  # Base64 encoded image
    commentaries: list[str] = []  # Commentary sources: mhc, calvincommentaries
    bulletin_pdf: str | None = None  # Base64 encoded bulletin PDF
    prayer_pdf: str | None = None  # Base64 encoded prayer requests PDF
    outline: SermonOutline | None = None            # pre-extracted outline (skips LLM if provided)
    commentary_overrides: list[SelectedCommentaryResult] = []  # user-selected commentary entries


class GenerateResponse(BaseModel):
    success: bool
    url: str | None = None
    tex_url: str | None = None
    error: str | None = None


def _hash_password(password: str) -> str:
    """Hash password for comparison."""
    return hashlib.sha256(password.encode()).hexdigest()


@router.post("/auth", response_model=AuthResponse)
async def authenticate(request: AuthRequest, response: Response):
    """Validate password and set session cookie."""
    settings = get_settings()

    # Auto-succeed in development mode
    if settings.is_development:
        token = secrets.token_urlsafe(32)
        _valid_sessions.add(token)
        _save_sessions(_valid_sessions)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            samesite="strict",
            max_age=86400
        )
        return AuthResponse(valid=True)

    if not settings.web_password:
        raise HTTPException(
            status_code=503,
            detail="Web password not configured. Set WEB_PASSWORD environment variable."
        )

    if request.password == settings.web_password:
        # Generate session token
        token = secrets.token_urlsafe(32)
        _valid_sessions.add(token)
        _save_sessions(_valid_sessions)

        # Set cookie (httponly for security)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            samesite="strict",
            max_age=86400  # 24 hours
        )

        return AuthResponse(valid=True)

    return AuthResponse(valid=False)


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
        outline=outline,
        candidates=candidates,
    )


@router.post("/generate", response_model=GenerateResponse)
async def generate_sermon_pdf(
    request: GenerateRequest,
    session: str | None = Cookie(default=None)
):
    """Generate sermon PDF from pasted notes and optional image."""
    settings = get_settings()

    # Skip auth in development mode
    if not settings.is_development:
        # Validate session
        if not session or session not in _valid_sessions:
            raise HTTPException(status_code=401, detail="Not authenticated")

    if not request.notes or not request.notes.strip():
        return GenerateResponse(success=False, error="No sermon notes provided")

    # Extract outline from text using LLM
    try:
        outline = await extract_sermon_outline_from_text(request.notes)
    except LLMError as exc:
        logger.error("LLM extraction failed: %s", exc)
        return GenerateResponse(success=False, error=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error during extraction")
        return GenerateResponse(success=False, error=f"Failed to parse notes: {exc}")

    # Handle cover image if provided
    cover_image_filename = None
    image_data = None

    if request.image:
        try:
            # Decode base64 image
            image_data = base64.b64decode(request.image)

            # Detect image format from magic bytes
            if image_data[:8] == b'\x89PNG\r\n\x1a\n':
                cover_image_filename = "cover.png"
            elif image_data[:2] == b'\xff\xd8':
                cover_image_filename = "cover.jpg"
            elif image_data[:4] == b'RIFF' and image_data[8:12] == b'WEBP':
                cover_image_filename = "cover.webp"
            else:
                # Default to png
                cover_image_filename = "cover.png"
        except Exception as exc:
            logger.warning("Failed to decode cover image: %s", exc)
            # Continue without image
            cover_image_filename = None
            image_data = None

    # Handle bulletin PDF if provided
    bulletin_data = None
    if request.bulletin_pdf:
        try:
            bulletin_data = base64.b64decode(request.bulletin_pdf)
            # Verify it's a PDF
            if not bulletin_data[:4] == b'%PDF':
                logger.warning("Bulletin file is not a valid PDF")
                bulletin_data = None
        except Exception as exc:
            logger.warning("Failed to decode bulletin PDF: %s", exc)
            bulletin_data = None

    # Handle prayer requests PDF if provided
    prayer_data = None
    if request.prayer_pdf:
        try:
            prayer_data = base64.b64decode(request.prayer_pdf)
            # Verify it's a PDF
            if not prayer_data[:4] == b'%PDF':
                logger.warning("Prayer requests file is not a valid PDF")
                prayer_data = None
        except Exception as exc:
            logger.warning("Failed to decode prayer requests PDF: %s", exc)
            prayer_data = None

    # Generate LaTeX
    logger.info("Generating LaTeX with commentary sources: %s", request.commentaries)
    try:
        latex_content = await generate_sermon_latex(
            outline=outline,
            scripture_version="ESV",
            subpoint_version="NET",
            include_main_passage=True,
            cover_image=cover_image_filename,
            commentary_sources=request.commentaries,
            include_bulletin=bulletin_data is not None,
            include_prayer_requests=prayer_data is not None
        )
    except Exception as exc:
        logger.exception("LaTeX generation failed")
        return GenerateResponse(success=False, error=f"Failed to generate document: {exc}")

    # Compile to PDF
    try:
        # Build supplementary files dict
        supplementary_pdfs = {}
        if bulletin_data:
            supplementary_pdfs["bulletin.pdf"] = bulletin_data
        if prayer_data:
            supplementary_pdfs["prayer_requests.pdf"] = prayer_data

        # If we have a cover image, we need to handle it specially
        # The compiler copies files to a temp directory, so we need to inject the image
        processed_tex = latex_content  # Default to unprocessed
        if cover_image_filename and image_data:
            # Create a custom compilation with the image
            pdf_bytes, log, processed_tex = await _compile_with_image(
                latex_content,
                cover_image_filename,
                image_data,
                supplementary_pdfs=supplementary_pdfs
            )
        else:
            # For non-image case, also get processed tex
            pdf_bytes, log, processed_tex = await _compile_without_image(
                latex_content,
                supplementary_pdfs=supplementary_pdfs
            )

        # Save PDF and tex, get URLs
        # Use sermon title as filename (sanitize for filesystem)
        safe_title = "".join(c for c in outline.metadata.title if c.isalnum() or c in " -_").strip()
        filename = f"{safe_title}.pdf" if safe_title else "sermon.pdf"
        pdf_id = await save_pdf(pdf_bytes, filename, tex_content=processed_tex)
        download_url = f"/download/{pdf_id}"
        tex_url = f"/download/{pdf_id}/tex"

        return GenerateResponse(success=True, url=download_url, tex_url=tex_url)

    except CompilationError as exc:
        logger.error("Compilation failed: %s", exc.message)
        if exc.log:
            # Log last 50 lines of compilation log for debugging
            log_lines = exc.log.split('\n')[-50:]
            logger.error("LaTeX log (last 50 lines):\n%s", '\n'.join(log_lines))
        return GenerateResponse(success=False, error=f"PDF compilation failed: {exc.message}")
    except Exception as exc:
        logger.exception("Unexpected compilation error")
        return GenerateResponse(success=False, error=f"Compilation error: {exc}")


async def _compile_without_image(
    latex_content: str,
    supplementary_pdfs: dict[str, bytes] | None = None
) -> tuple[bytes, str, str]:
    """Compile LaTeX without cover image.

    Returns: (pdf_bytes, log_output, processed_tex_content)
    """
    import asyncio
    import os
    import shutil
    from ..config import get_settings
    from ..placeholders import process_scripture_placeholders

    settings = get_settings()
    work_dir = Path(tempfile.mkdtemp(prefix="latexgen_"))

    try:
        # Write LaTeX file
        tex_file = work_dir / "sermon.tex"
        tex_file.write_text(latex_content, encoding="utf-8")

        # Copy global styles and fonts
        styles_dir = Path(settings.storage_path) / "styles"
        fonts_dir = Path(settings.storage_path) / "fonts"

        if styles_dir.exists():
            for style_file in styles_dir.glob("*"):
                shutil.copy(style_file, work_dir / style_file.name)

        if fonts_dir.exists():
            for font_file in fonts_dir.glob("*"):
                shutil.copy(font_file, work_dir / font_file.name)

        # Write supplementary PDFs
        if supplementary_pdfs:
            for filename, pdf_data in supplementary_pdfs.items():
                pdf_path = work_dir / filename
                pdf_path.write_bytes(pdf_data)

        # Process scripture placeholders
        await process_scripture_placeholders(work_dir, "sermon.tex")

        # Read the processed tex content AFTER placeholder processing
        processed_tex = tex_file.read_text(encoding="utf-8")

        # Compile with LuaLaTeX (twice for references)
        log_output = ""
        for run in range(2):
            proc = await asyncio.create_subprocess_exec(
                "lualatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "sermon.tex",
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "TEXMFHOME": str(work_dir)}
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=120
            )
            log_output = stdout.decode(errors="replace")

            if proc.returncode != 0:
                raise CompilationError(
                    f"LaTeX compilation failed (run {run + 1})",
                    log=log_output
                )

        # Read output PDF
        pdf_path = work_dir / "sermon.pdf"
        if not pdf_path.exists():
            raise CompilationError("PDF was not generated", log=log_output)

        pdf_bytes = pdf_path.read_bytes()
        return pdf_bytes, log_output, processed_tex

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


async def _compile_with_image(
    latex_content: str,
    image_filename: str,
    image_data: bytes,
    supplementary_pdfs: dict[str, bytes] | None = None
) -> tuple[bytes, str, str]:
    """Compile LaTeX with cover image injected into work directory.

    Returns: (pdf_bytes, log_output, processed_tex_content)
    """
    import asyncio
    import os
    import shutil
    from ..config import get_settings
    from ..placeholders import process_scripture_placeholders

    settings = get_settings()
    work_dir = Path(tempfile.mkdtemp(prefix="latexgen_"))

    try:
        # Write LaTeX file
        tex_file = work_dir / "sermon.tex"
        tex_file.write_text(latex_content, encoding="utf-8")

        # Write cover image
        image_path = work_dir / image_filename
        image_path.write_bytes(image_data)

        # Copy global styles and fonts
        styles_dir = Path(settings.storage_path) / "styles"
        fonts_dir = Path(settings.storage_path) / "fonts"

        if styles_dir.exists():
            for style_file in styles_dir.glob("*"):
                shutil.copy(style_file, work_dir / style_file.name)

        if fonts_dir.exists():
            for font_file in fonts_dir.glob("*"):
                shutil.copy(font_file, work_dir / font_file.name)

        # Write supplementary PDFs
        if supplementary_pdfs:
            for filename, pdf_data in supplementary_pdfs.items():
                pdf_path = work_dir / filename
                pdf_path.write_bytes(pdf_data)

        # Process scripture placeholders
        await process_scripture_placeholders(work_dir, "sermon.tex")

        # Read the processed tex content AFTER placeholder processing
        processed_tex = tex_file.read_text(encoding="utf-8")

        # Compile with LuaLaTeX (twice for references)
        log_output = ""
        for run in range(2):
            proc = await asyncio.create_subprocess_exec(
                "lualatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "sermon.tex",
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "TEXMFHOME": str(work_dir)}
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=120
            )
            log_output = stdout.decode(errors="replace")

            if proc.returncode != 0:
                raise CompilationError(
                    f"LaTeX compilation failed (run {run + 1})",
                    log=log_output
                )

        # Read output PDF
        pdf_path = work_dir / "sermon.pdf"
        if not pdf_path.exists():
            raise CompilationError("PDF was not generated", log=log_output)

        pdf_bytes = pdf_path.read_bytes()
        return pdf_bytes, log_output, processed_tex

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@router.post("/logout")
async def logout(response: Response, session: str | None = Cookie(default=None)):
    """Clear session cookie."""
    if session and session in _valid_sessions:
        _valid_sessions.discard(session)
        _save_sessions(_valid_sessions)

    response.delete_cookie(key="session")
    return {"success": True}
