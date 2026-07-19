import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .models import HealthResponse
from .compiler import check_latex_available
from .storage import get_pdf, get_tex, cleanup_expired_pdfs
from .routes import compile, styles, fonts, packages, scripture, sermon_notes, web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="LaTeXGen",
    description="""
A web service for compiling LaTeX documents to PDF.

## Features
- Compile LaTeX to PDF from various input formats
- Support for custom styles and fonts
- Manage TeX packages

## Input Formats
- **Single file**: Base64-encoded .tex content
- **Multiple files**: Array of files with base64 content
- **ZIP archive**: Base64-encoded .zip with all resources

## Authentication
Include your API key in the `X-API-Key` header.
""",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    servers=[
        {"url": "http://localhost:8000", "description": "Local development server"}
    ]
)

# Browsers don't treat 0.0.0.0 as a trustworthy origin (unlike localhost), so
# downloads from it get stuck behind an "insecure download" gate. Redirect to
# localhost so links clicked from uvicorn's startup log still work.
@app.middleware("http")
async def redirect_0000_to_localhost(request: Request, call_next):
    host, _, port = request.headers.get("host", "").partition(":")
    if host == "0.0.0.0":
        netloc = f"localhost:{port}" if port else "localhost"
        url = request.url.replace(netloc=netloc)
        return RedirectResponse(str(url), status_code=307)
    return await call_next(request)


# CORS for ChatGPT and other integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(compile.router)
app.include_router(styles.router)
app.include_router(fonts.router)
app.include_router(packages.router)
app.include_router(scripture.router)
app.include_router(sermon_notes.router)
app.include_router(web.router)

# Mount static files for web frontend
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/health", response_model=HealthResponse, tags=["utility"])
async def health_check():
    """Check service health and LaTeX availability."""
    latex_ok, version = await check_latex_available()

    return HealthResponse(
        status="ok" if latex_ok else "degraded",
        latex_available=latex_ok,
        version=version
    )


@app.get("/", include_in_schema=False)
async def root():
    """Serve the web frontend."""
    index_path = Path(__file__).parent / "static" / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "LaTeXGen API", "docs": "/docs"}


# Must be registered before the /{slug} route below, or /tex matches the slug.
@app.get("/download/{pdf_id}/tex", tags=["utility"], summary="Download LaTeX source")
async def download_tex(pdf_id: str):
    """
    Download the LaTeX source file for a compiled PDF.
    """
    result = get_tex(pdf_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="TeX file not found or expired."
        )

    tex_path, filename = result
    return FileResponse(
        path=tex_path,
        media_type="application/x-tex",
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/download/{pdf_id}", tags=["utility"], summary="Download a compiled PDF")
@app.get("/download/{pdf_id}/{slug}", tags=["utility"], include_in_schema=False)
async def download_pdf(pdf_id: str, slug: str = ""):
    """
    Download a previously compiled PDF by its ID.
    PDFs are stored for 7 days after compilation.
    The optional /{slug} suffix (e.g. /sermon.pdf) helps browsers infer the file type.
    """
    result = get_pdf(pdf_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="PDF not found or expired. PDFs are deleted after 7 days."
        )

    pdf_path, filename = result
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.on_event("startup")
async def startup_cleanup():
    """Clean up expired PDFs on startup."""
    removed = cleanup_expired_pdfs()
    if removed > 0:
        logger.info(f"Cleaned up {removed} expired PDF(s)")
