import base64
import logging
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse

from ..models import CompileRequest, CompileResponse, OutputFormat
from ..compiler import compile_latex, CompilationError
from ..storage import save_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compile", tags=["compile"])


@router.post(
    "",
    response_model=CompileResponse,
    responses={
        200: {
            "description": "Successful compilation",
            "content": {
                "application/json": {
                    "examples": {
                        "base64": {
                            "summary": "Base64 output",
                            "value": {"success": True, "pdf": "JVBERi0xLjQK...", "log": "..."}
                        },
                        "url": {
                            "summary": "URL output",
                            "value": {"success": True, "url": "https://latexifier-production.up.railway.app/download/abc-123", "log": "..."}
                        }
                    }
                },
                "application/pdf": {}
            }
        },
        400: {"description": "Invalid request"},
        500: {"description": "Compilation failed"}
    },
    summary="Compile LaTeX to PDF",
    description="Compile LaTeX to PDF. Provide ONE of: content, files, or zip. Set output_format to pdf, base64, or url."
)
async def compile_document(request: CompileRequest):
    # Log incoming request for debugging
    logger.info(f"Compile request: engine={request.engine}, output_format={request.output_format}, "
                f"has_content={request.content is not None}, has_files={request.files is not None}, "
                f"has_zip={request.zip is not None}, main_file={request.main_file}")

    # Validate input - exactly one source must be provided
    sources = [request.content, request.files, request.zip]
    provided = sum(1 for s in sources if s is not None)

    if provided == 0:
        raise HTTPException(
            status_code=400,
            detail="No input provided. Supply content, files, or zip."
        )
    if provided > 1:
        raise HTTPException(
            status_code=400,
            detail="Multiple inputs provided. Supply only one of: content, files, or zip."
        )

    try:
        pdf_bytes, log = await compile_latex(request)

        # Determine output filename
        if request.content:
            out_filename = request.filename.rsplit(".", 1)[0] + ".pdf"
        else:
            out_filename = request.main_file.rsplit(".", 1)[0] + ".pdf"

        if request.output_format == OutputFormat.PDF:
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename={out_filename}"
                }
            )
        elif request.output_format == OutputFormat.URL:
            # Store PDF and return download URL
            pdf_id = await save_pdf(pdf_bytes, out_filename)
            download_url = f"https://latexifier-production.up.railway.app/download/{pdf_id}"
            logger.info(f"PDF stored with ID {pdf_id}")
            return CompileResponse(
                success=True,
                url=download_url,
                log=log
            )
        else:
            # BASE64 format
            pdf_base64 = base64.b64encode(pdf_bytes).decode()
            return CompileResponse(
                success=True,
                pdf=pdf_base64,
                log=log
            )

    except CompilationError as e:
        logger.error(f"Compilation failed: {e.message}")
        logger.debug(f"Compilation log: {e.log[:500] if e.log else 'No log'}")
        return JSONResponse(
            status_code=500,
            content=CompileResponse(
                success=False,
                error=e.message,
                log=e.log
            ).model_dump()
        )
    except Exception as e:
        logger.exception(f"Unexpected error during compilation: {e}")
        return JSONResponse(
            status_code=500,
            content=CompileResponse(
                success=False,
                error=str(e),
                log=None
            ).model_dump()
        )
