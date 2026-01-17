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
    include_commentary: bool = Field(
        False,
        description="Include commentary appendix for scripture placeholders"
    )
    commentary_sources: list[str] = Field(
        default_factory=list,
        description="Commentary sources: mhc, calvincommentaries"
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


# Sermon Notes Models

class SermonMetadata(BaseModel):
    """Extracted metadata from sermon notes."""
    title: str = Field(..., description="Sermon title")
    speaker: str | None = Field(None, description="Speaker/pastor name")
    date: str | None = Field(None, description="Sermon date")
    series: str | None = Field(None, description="Sermon series name if mentioned")


class SermonSubPoint(BaseModel):
    """A sub-point or bullet within a main point."""
    label: str | None = Field(None, description="Label like 'A', 'B', or bullet marker")
    title: str | None = Field(None, description="Sub-point title if present")
    content: str | None = Field(None, description="The sub-point content/explanation")
    bullets: list[str] = Field(default_factory=list, description="Bullet points for this sub-point")
    scripture_verse: str | None = Field(None, description="Specific verse(s) from main passage for this sub-point")
    scripture_refs: list[str] = Field(default_factory=list, description="Scripture references mentioned")


class SermonPoint(BaseModel):
    """A main sermon point with optional sub-points."""
    number: int = Field(..., description="Point number (1, 2, 3...)")
    title: str = Field(..., description="Main point title")
    content: str | None = Field(None, description="Content directly under the main point")
    bullets: list[str] = Field(default_factory=list, description="Simple bullet points (not lettered sub-points)")
    numbered_items: list[str] = Field(default_factory=list, description="Numbered/enumerated list items")
    sub_points: list[SermonSubPoint] = Field(default_factory=list)
    scripture_refs: list[str] = Field(default_factory=list, description="Scripture references for this point")


class SermonOutline(BaseModel):
    """Complete parsed sermon structure."""
    metadata: SermonMetadata
    main_passage: str = Field(..., description="Primary scripture passage (e.g., 'James 3:1-12')")
    foundational_principle: str | None = Field(None, description="Key principle or thesis statement")
    foundational_scripture: str | None = Field(None, description="Scripture for foundational principle")
    points: list[SermonPoint] = Field(default_factory=list)
    all_scripture_refs: list[str] = Field(default_factory=list, description="All unique scripture references")


class CommentarySourceEnum(str, Enum):
    """Available commentary sources."""
    MHC = "mhc"  # Matthew Henry's Complete Commentary
    CALVIN = "calvincommentaries"  # Calvin's Collected Commentaries
    BOTH = "both"  # Include both commentaries


class SermonNotesRequest(BaseModel):
    """Request to parse sermon notes."""
    pdf: str = Field(..., description="Base64-encoded PDF of sermon notes")
    output_format: OutputFormat = Field(
        OutputFormat.LATEX,
        description="Output format: latex, pdf, base64, or url"
    )
    scripture_version: str = Field(
        "ESV",
        description="Bible version for scripture placeholders"
    )
    include_main_passage: bool = Field(
        True,
        description="Include full text of main passage at the beginning"
    )
    include_commentary: bool = Field(
        False,
        description="Include commentary appendix for scripture references"
    )
    commentary_source: CommentarySourceEnum = Field(
        CommentarySourceEnum.MHC,
        description="Commentary source: mhc (Matthew Henry), calvincommentaries (Calvin), or both"
    )
    engine: TexEngine = Field(
        TexEngine.LUALATEX,
        description="LaTeX engine for PDF compilation (lualatex required for custom fonts)"
    )


class SermonNotesResponse(BaseModel):
    """Response from sermon notes parsing."""
    success: bool
    outline: SermonOutline | None = Field(None, description="Parsed sermon structure")
    latex: str | None = Field(None, description="Generated LaTeX source")
    pdf: str | None = Field(None, description="Base64 PDF if output_format=base64")
    url: str | None = Field(None, description="Download URL if output_format=url")
    error: str | None = None
    log: str | None = None
