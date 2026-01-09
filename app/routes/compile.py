import base64
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse

from ..models import CompileRequest, CompileResponse, OutputFormat
from ..compiler import compile_latex, CompilationError

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
    description="""
Compile LaTeX source to PDF. Accepts three input formats:

1. **Single file**: Provide `content` with base64-encoded .tex file
2. **Multiple files**: Provide `files` array with name/content pairs
3. **ZIP archive**: Provide `zip` with base64-encoded .zip file

Set `output_format` to 'pdf' for raw PDF bytes or 'base64' for JSON response.
"""
)
async def compile_document(request: CompileRequest):
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
        return JSONResponse(
            status_code=500,
            content=CompileResponse(
                success=False,
                error=e.message,
                log=e.log
            ).model_dump()
        )
