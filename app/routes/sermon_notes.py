import base64
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..compiler import compile_latex, CompilationError
from ..llm import extract_sermon_outline, LLMError
from ..models import (
    SermonNotesRequest,
    SermonNotesResponse,
    OutputFormat,
    CompileRequest,
    CommentarySourceEnum,
)
from ..sermon_latex import generate_sermon_latex
from ..storage import save_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sermon-notes", tags=["sermon-notes"])


@router.post(
    "",
    response_model=SermonNotesResponse,
    responses={
        200: {
            "description": "Successfully parsed sermon notes",
            "content": {
                "application/json": {
                    "examples": {
                        "latex": {
                            "summary": "LaTeX output",
                            "value": {
                                "success": True,
                                "outline": {"metadata": {"title": "..."}, "main_passage": "James 3:1-12"},
                                "latex": "\\documentclass{article}..."
                            }
                        },
                        "base64": {
                            "summary": "Base64 PDF output",
                            "value": {
                                "success": True,
                                "outline": {"metadata": {"title": "..."}},
                                "pdf": "JVBERi0xLjQK..."
                            }
                        }
                    }
                }
            }
        },
        400: {"description": "Invalid request"},
        502: {"description": "LLM API error"},
        500: {"description": "Processing failed"}
    },
    summary="Parse sermon notes PDF",
    description="""
Upload a PDF of sermon notes and extract structured content using AI.

The endpoint:
1. Accepts a base64-encoded PDF
2. Uses Claude to extract sermon structure (title, speaker, date, outline, scripture refs)
3. Generates LaTeX with [[scripture:...]] placeholders
4. Optionally compiles to PDF

Scripture placeholders are processed during compilation to fetch actual passage text.
"""
)
async def parse_sermon_notes(request: SermonNotesRequest):
    """Parse sermon notes from PDF and generate LaTeX output."""

    # Decode the PDF
    try:
        pdf_bytes = base64.b64decode(request.pdf)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid base64 PDF data: {exc}"
        )

    # Validate it looks like a PDF
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=400,
            detail="Data does not appear to be a valid PDF"
        )

    # Extract sermon outline using Claude
    try:
        outline = await extract_sermon_outline(pdf_bytes)
    except LLMError as exc:
        logger.error("LLM extraction failed: %s", exc)
        return SermonNotesResponse(
            success=False,
            error=str(exc)
        )
    except Exception as exc:
        logger.exception("Unexpected error during extraction")
        return SermonNotesResponse(
            success=False,
            error=f"Failed to extract sermon outline: {exc}"
        )

    # Generate LaTeX
    try:
        latex_content = generate_sermon_latex(
            outline=outline,
            scripture_version=request.scripture_version,
            include_main_passage=request.include_main_passage
        )
    except Exception as exc:
        logger.exception("LaTeX generation failed")
        return SermonNotesResponse(
            success=False,
            outline=outline,
            error=f"Failed to generate LaTeX: {exc}"
        )

    # If only LaTeX requested, return now
    if request.output_format == OutputFormat.LATEX:
        return SermonNotesResponse(
            success=True,
            outline=outline,
            latex=latex_content
        )

    # Compile to PDF
    try:
        # Determine commentary sources to include
        commentary_sources = []
        if request.include_commentary:
            if request.commentary_source == CommentarySourceEnum.BOTH:
                commentary_sources = ["mhc", "calvincommentaries"]
            else:
                commentary_sources = [request.commentary_source.value]

        compile_request = CompileRequest(
            content=latex_content,
            filename="sermon.tex",
            engine=request.engine,
            output_format=OutputFormat.BASE64,  # Always get bytes internally
            include_commentary=request.include_commentary,
            commentary_sources=commentary_sources
        )

        pdf_result, log = await compile_latex(compile_request)

        # Handle output format
        if request.output_format == OutputFormat.PDF:
            # Return raw PDF
            return Response(
                content=pdf_result,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": "attachment; filename=sermon.pdf"
                }
            )
        elif request.output_format == OutputFormat.URL:
            pdf_id = await save_pdf(pdf_result, "sermon.pdf")
            download_url = f"https://latexifier-production.up.railway.app/download/{pdf_id}"
            return SermonNotesResponse(
                success=True,
                outline=outline,
                latex=latex_content,
                url=download_url,
                log=log
            )
        else:  # BASE64
            pdf_base64 = base64.b64encode(pdf_result).decode()
            return SermonNotesResponse(
                success=True,
                outline=outline,
                latex=latex_content,
                pdf=pdf_base64,
                log=log
            )

    except CompilationError as exc:
        logger.error("Compilation failed: %s", exc.message)
        return SermonNotesResponse(
            success=False,
            outline=outline,
            latex=latex_content,
            error=f"LaTeX compilation failed: {exc.message}",
            log=exc.log
        )
    except Exception as exc:
        logger.exception("Unexpected compilation error")
        return SermonNotesResponse(
            success=False,
            outline=outline,
            latex=latex_content,
            error=f"Compilation error: {exc}"
        )
