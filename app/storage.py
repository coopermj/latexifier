import os
import shutil
from pathlib import Path

import aiofiles

from .config import get_settings


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
