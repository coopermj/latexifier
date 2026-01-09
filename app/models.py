from pydantic import BaseModel, Field
from enum import Enum


class OutputFormat(str, Enum):
    PDF = "pdf"
    BASE64 = "base64"


class TexEngine(str, Enum):
    PDFLATEX = "pdflatex"
    XELATEX = "xelatex"
    LUALATEX = "lualatex"


class FileItem(BaseModel):
    name: str = Field(..., description="Filename including extension")
    content: str = Field(..., description="Base64-encoded file content")


class CompileRequest(BaseModel):
    """Request to compile LaTeX to PDF.

    Provide ONE of: content (single file), files (multiple files), or zip (archive).
    """
    content: str | None = Field(
        None,
        description="Base64-encoded LaTeX content (for single file)"
    )
    filename: str = Field(
        "document.tex",
        description="Filename for single file mode"
    )
    files: list[FileItem] | None = Field(
        None,
        description="List of files with base64 content (for multi-file)"
    )
    zip: str | None = Field(
        None,
        description="Base64-encoded ZIP archive"
    )
    main_file: str = Field(
        "main.tex",
        description="Main .tex file to compile (for multi-file/zip)"
    )
    output_format: OutputFormat = Field(
        OutputFormat.BASE64,
        description="Output format: 'pdf' for raw bytes, 'base64' for JSON"
    )
    engine: TexEngine = Field(
        TexEngine.PDFLATEX,
        description="TeX engine: 'pdflatex' (default), 'xelatex' (for fontspec/custom fonts), or 'lualatex'"
    )


class CompileResponse(BaseModel):
    success: bool
    pdf: str | None = Field(None, description="Base64-encoded PDF (if output_format=base64)")
    error: str | None = Field(None, description="Error message if compilation failed")
    log: str | None = Field(None, description="LaTeX compilation log")


class StyleInfo(BaseModel):
    name: str
    filename: str
    uploaded_at: str


class FontInfo(BaseModel):
    name: str
    filename: str
    uploaded_at: str


class HealthResponse(BaseModel):
    status: str = "ok"
    latex_available: bool
    version: str | None = None
