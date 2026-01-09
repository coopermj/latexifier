import os
import shutil
import time
import uuid
from pathlib import Path

import aiofiles

from .config import get_settings

# PDF outputs expire after 7 days (in seconds)
PDF_EXPIRY_SECONDS = 7 * 24 * 60 * 60


def get_storage_path() -> Path:
    """Get the base storage path."""
    settings = get_settings()
    path = Path(settings.storage_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_styles_path() -> Path:
    """Get the styles storage path."""
    path = get_storage_path() / "styles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_fonts_path() -> Path:
    """Get the fonts storage path."""
    path = get_storage_path() / "fonts"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_style(filename: str, content: bytes) -> Path:
    """Save a style file to storage."""
    path = get_styles_path() / filename
    async with aiofiles.open(path, "wb") as f:
        await f.write(content)
    return path


async def save_font(filename: str, content: bytes) -> Path:
    """Save a font file to storage."""
    path = get_fonts_path() / filename
    async with aiofiles.open(path, "wb") as f:
        await f.write(content)
    return path


def delete_style(filename: str) -> bool:
    """Delete a style file from storage."""
    path = get_styles_path() / filename
    if path.exists():
        path.unlink()
        return True
    return False


def delete_font(filename: str) -> bool:
    """Delete a font file from storage."""
    path = get_fonts_path() / filename
    if path.exists():
        path.unlink()
        return True
    return False


def list_styles() -> list[str]:
    """List all style files."""
    path = get_styles_path()
    return [f.name for f in path.iterdir() if f.is_file()]


def list_fonts() -> list[str]:
    """List all font files."""
    path = get_fonts_path()
    return [f.name for f in path.iterdir() if f.is_file()]


def get_outputs_path() -> Path:
    """Get the PDF outputs storage path."""
    path = get_storage_path() / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_pdf(content: bytes, filename: str = "document.pdf") -> str:
    """
    Save a compiled PDF to storage with a unique ID.
    Returns the ID for later retrieval.
    """
    pdf_id = str(uuid.uuid4())
    # Store with original filename for Content-Disposition
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
    if not safe_filename.endswith(".pdf"):
        safe_filename += ".pdf"

    # Create directory for this PDF (stores metadata)
    pdf_dir = get_outputs_path() / pdf_id
    pdf_dir.mkdir(parents=True, exist_ok=True)

    # Save PDF
    pdf_path = pdf_dir / safe_filename
    async with aiofiles.open(pdf_path, "wb") as f:
        await f.write(content)

    return pdf_id


def get_pdf(pdf_id: str) -> tuple[Path, str] | None:
    """
    Get a stored PDF by ID.
    Returns (path, filename) or None if not found/expired.
    """
    pdf_dir = get_outputs_path() / pdf_id
    if not pdf_dir.exists():
        return None

    # Find the PDF file in the directory
    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        return None

    pdf_path = pdf_files[0]

    # Check if expired
    age = time.time() - pdf_path.stat().st_mtime
    if age > PDF_EXPIRY_SECONDS:
        # Clean up expired file
        shutil.rmtree(pdf_dir, ignore_errors=True)
        return None

    return pdf_path, pdf_path.name


def cleanup_expired_pdfs() -> int:
    """
    Remove PDFs older than 7 days.
    Returns count of removed files.
    """
    outputs_path = get_outputs_path()
    removed = 0

    for pdf_dir in outputs_path.iterdir():
        if not pdf_dir.is_dir():
            continue

        # Check age based on directory modification time
        try:
            age = time.time() - pdf_dir.stat().st_mtime
            if age > PDF_EXPIRY_SECONDS:
                shutil.rmtree(pdf_dir, ignore_errors=True)
                removed += 1
        except Exception:
            pass

    return removed
