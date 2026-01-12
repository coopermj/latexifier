from pydantic import BaseModel, Field
from enum import Enum


class OutputFormat(str, Enum):
    PDF = "pdf"
    BASE64 = "base64"
    URL = "url"
    LATEX = "latex"


class TexEngine(str, Enum):
    PDFLATEX = "pdflatex"
    XELATEX = "xelatex"
    LUALATEX = "lualatex"
    QUARTO = "quarto"


class FileItem(BaseModel):
    name: str = Field(..., description="Filename including extension")
    content: str = Field(..., description="File content: raw text or base64-encoded")


class CompileRequest(BaseModel):
    """Request to compile LaTeX to PDF.

    Provide ONE of: content (single file), files (multiple files), or zip (archive).
    """
    content: str | None = Field(
        None,
        description="LaTeX content: raw text or base64-encoded"
    )
    filename: str = Field(
        "document.tex",
        description="Filename for single file mode"
    )
    files: list[FileItem] | None = Field(
        None,
        description="List of files (content can be raw text or base64)"
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
        description="Output: pdf, base64, url, or latex (quarto only)"
    )
    engine: TexEngine = Field(
        TexEngine.PDFLATEX,
        description="Engine: pdflatex, xelatex, lualatex, or quarto (for .qmd files)"
    )


class CompileResponse(BaseModel):
    success: bool
    pdf: str | None = Field(None, description="Base64-encoded PDF (if output_format=base64)")
    url: str | None = Field(None, description="Download URL (if output_format=url)")
    latex: str | None = Field(None, description="LaTeX source (if output_format=latex, quarto only)")
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
