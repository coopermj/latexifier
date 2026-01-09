import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .models import HealthResponse
from .compiler import check_latex_available
from .routes import compile, styles, fonts, packages

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
        {"url": "https://latexifier-production.up.railway.app", "description": "Production server"}
    ]
)

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
    """Redirect to docs."""
    return {"message": "LaTeXGen API", "docs": "/docs"}
