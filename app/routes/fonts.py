import base64
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import RequireAPIKey
from ..database import get_session, Font
from ..storage import save_font, delete_font, get_fonts_path
from ..models import FontInfo

router = APIRouter(prefix="/fonts", tags=["fonts"])


@router.get("", response_model=list[FontInfo], summary="List available fonts")
async def list_fonts(
    _: RequireAPIKey,
    session: AsyncSession = Depends(get_session)
):
    """List all available custom fonts."""
    result = await session.execute(select(Font).order_by(Font.name))
    fonts = result.scalars().all()
    return [
        FontInfo(
            name=f.name,
            filename=f.filename,
            uploaded_at=f.uploaded_at.isoformat()
        )
        for f in fonts
    ]


@router.post("", response_model=FontInfo, summary="Upload a font file")
async def upload_font(
    _: RequireAPIKey,
    session: AsyncSession = Depends(get_session),
    file: UploadFile | None = File(None),
    name: str | None = Form(None),
    content: str | None = Form(None),
    filename: str | None = Form(None)
):
    """
    Upload a custom font file (.ttf, .otf, .woff, etc.).

    Either upload a file directly or provide base64-encoded content.
    """
    if file:
        # File upload mode
        file_content = await file.read()
        file_name = file.filename
        font_name = name or file_name.rsplit(".", 1)[0]
    elif content and filename:
        # Base64 mode
        file_content = base64.b64decode(content)
        file_name = filename
        font_name = name or filename.rsplit(".", 1)[0]
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either a file upload or content+filename"
        )

    # Validate file extension
    valid_extensions = (".ttf", ".otf", ".woff", ".woff2", ".pfb", ".pfm")
    if not file_name.lower().endswith(valid_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"Font files must have one of these extensions: {', '.join(valid_extensions)}"
        )

    # Check if font already exists
    existing = await session.execute(
        select(Font).where(Font.name == font_name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Font '{font_name}' already exists. Delete it first to replace."
        )

    # Save file and database record
    await save_font(file_name, file_content)

    font = Font(name=font_name, filename=file_name)
    session.add(font)
    await session.commit()
    await session.refresh(font)

    return FontInfo(
        name=font.name,
        filename=font.filename,
        uploaded_at=font.uploaded_at.isoformat()
    )


@router.delete("/{name}", summary="Delete a font")
async def remove_font(
    name: str,
    _: RequireAPIKey,
    session: AsyncSession = Depends(get_session)
):
    """Delete a custom font by name."""
    result = await session.execute(
        select(Font).where(Font.name == name)
    )
    font = result.scalar_one_or_none()

    if not font:
        raise HTTPException(status_code=404, detail=f"Font '{name}' not found")

    delete_font(font.filename)
    await session.execute(delete(Font).where(Font.id == font.id))
    await session.commit()

    return {"message": f"Font '{name}' deleted"}
