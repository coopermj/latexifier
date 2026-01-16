"""Web interface routes for sermon notes processing."""
import base64
import hashlib
import logging
import secrets
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Cookie, Response
from pydantic import BaseModel

from ..compiler import compile_latex, CompilationError
from ..config import get_settings
from ..llm import extract_sermon_outline_from_text, LLMError
from ..models import CompileRequest, TexEngine, OutputFormat
from ..sermon_latex import generate_sermon_latex
from ..storage import save_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/web", tags=["web"])

# Simple in-memory session storage (tokens valid for session)
_valid_sessions: set[str] = set()


class AuthRequest(BaseModel):
    password: str


class AuthResponse(BaseModel):
    valid: bool


class GenerateRequest(BaseModel):
    notes: str
    image: str | None = None  # Base64 encoded image
    commentaries: list[str] = []  # Commentary sources: mhc, calvincommentaries


class GenerateResponse(BaseModel):
    success: bool
    url: str | None = None
    error: str | None = None


def _hash_password(password: str) -> str:
    """Hash password for comparison."""
    return hashlib.sha256(password.encode()).hexdigest()


@router.post("/auth", response_model=AuthResponse)
async def authenticate(request: AuthRequest, response: Response):
    """Validate password and set session cookie."""
    settings = get_settings()

    if not settings.web_password:
        raise HTTPException(
            status_code=503,
            detail="Web password not configured. Set WEB_PASSWORD environment variable."
        )

    if request.password == settings.web_password:
        # Generate session token
        token = secrets.token_urlsafe(32)
        _valid_sessions.add(token)

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


@router.post("/generate", response_model=GenerateResponse)
async def generate_sermon_pdf(
    request: GenerateRequest,
    session: str | None = Cookie(default=None)
):
    """Generate sermon PDF from pasted notes and optional image."""
    settings = get_settings()

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

    # Generate LaTeX
    logger.info("Generating LaTeX with commentary sources: %s", request.commentaries)
    try:
        latex_content = await generate_sermon_latex(
            outline=outline,
            scripture_version="ESV",
            subpoint_version="NET",
            include_main_passage=True,
            cover_image=cover_image_filename,
            commentary_sources=request.commentaries
        )
    except Exception as exc:
        logger.exception("LaTeX generation failed")
        return GenerateResponse(success=False, error=f"Failed to generate document: {exc}")

    # Compile to PDF
    try:
        compile_request = CompileRequest(
            content=latex_content,
            filename="sermon.tex",
            engine=TexEngine.LUALATEX,
            output_format=OutputFormat.BASE64
        )

        # If we have a cover image, we need to handle it specially
        # The compiler copies files to a temp directory, so we need to inject the image
        if cover_image_filename and image_data:
            # Create a custom compilation with the image
            pdf_bytes, log = await _compile_with_image(
                latex_content,
                cover_image_filename,
                image_data
            )
        else:
            pdf_result, log = await compile_latex(compile_request)
            pdf_bytes = pdf_result

        # Save PDF and get URL
        pdf_id = await save_pdf(pdf_bytes, "sermon.pdf")
        download_url = f"/download/{pdf_id}"

        return GenerateResponse(success=True, url=download_url)

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


async def _compile_with_image(
    latex_content: str,
    image_filename: str,
    image_data: bytes
) -> tuple[bytes, str]:
    """Compile LaTeX with cover image injected into work directory."""
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

        # Process scripture placeholders
        await process_scripture_placeholders(work_dir, "sermon.tex")

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
        return pdf_bytes, log_output

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@router.post("/logout")
async def logout(response: Response, session: str | None = Cookie(default=None)):
    """Clear session cookie."""
    if session and session in _valid_sessions:
        _valid_sessions.discard(session)

    response.delete_cookie(key="session")
    return {"success": True}
