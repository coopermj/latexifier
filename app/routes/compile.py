import base64
import logging
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse

from ..models import CompileRequest, CompileResponse, OutputFormat
from ..compiler import compile_latex, CompilationError

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
                    "example": {
                        "success": True,
                        "pdf": "JVBERi0xLjQK...",
                        "error": None,
                        "log": "..."
                    }
                },
                "application/pdf": {}
            }
        },
        400: {"description": "Invalid request"},
        500: {"description": "Compilation failed"}
    },
    summary="Compile LaTeX to PDF",
    description="Compile LaTeX to PDF. Provide ONE of: content (base64 .tex), files (array), or zip (base64 archive). Set output_format to pdf or base64."
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

        if request.output_format == OutputFormat.PDF:
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": "attachment; filename=output.pdf"
                }
            )
        else:
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
