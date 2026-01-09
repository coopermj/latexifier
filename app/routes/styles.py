import base64
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import RequireAPIKey
from ..database import get_session, Style
from ..storage import save_style, delete_style, get_styles_path
from ..models import StyleInfo

router = APIRouter(prefix="/styles", tags=["styles"])


@router.get("", response_model=list[StyleInfo], summary="List available styles")
async def list_styles(
    _: RequireAPIKey,
    session: AsyncSession = Depends(get_session)
):
    """List all available custom LaTeX style files."""
    result = await session.execute(select(Style).order_by(Style.name))
    styles = result.scalars().all()
    return [
        StyleInfo(
            name=s.name,
            filename=s.filename,
            uploaded_at=s.uploaded_at.isoformat()
        )
        for s in styles
    ]


@router.post("", response_model=StyleInfo, summary="Upload a style file")
async def upload_style(
    _: RequireAPIKey,
    session: AsyncSession = Depends(get_session),
    file: UploadFile | None = File(None),
    name: str | None = Form(None),
    content: str | None = Form(None),
    filename: str | None = Form(None)
):
    """
    Upload a custom LaTeX style file (.sty or .cls).

    Either upload a file directly or provide base64-encoded content.
    """
    if file:
        # File upload mode
        file_content = await file.read()
        file_name = file.filename
        style_name = name or file_name.rsplit(".", 1)[0]
    elif content and filename:
        # Base64 mode
        file_content = base64.b64decode(content)
        file_name = filename
        style_name = name or filename.rsplit(".", 1)[0]
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either a file upload or content+filename"
        )

    # Validate file extension
    if not file_name.endswith((".sty", ".cls", ".tex")):
        raise HTTPException(
            status_code=400,
            detail="Style files must have .sty, .cls, or .tex extension"
        )

    # Check if style already exists
    existing = await session.execute(
        select(Style).where(Style.name == style_name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Style '{style_name}' already exists. Delete it first to replace."
        )

    # Save file and database record
    await save_style(file_name, file_content)

    style = Style(name=style_name, filename=file_name)
    session.add(style)
    await session.commit()
    await session.refresh(style)

    return StyleInfo(
        name=style.name,
        filename=style.filename,
        uploaded_at=style.uploaded_at.isoformat()
    )


@router.delete("/{name}", summary="Delete a style")
async def remove_style(
    name: str,
    _: RequireAPIKey,
    session: AsyncSession = Depends(get_session)
):
    """Delete a custom style by name."""
    result = await session.execute(
        select(Style).where(Style.name == name)
    )
    style = result.scalar_one_or_none()

    if not style:
        raise HTTPException(status_code=404, detail=f"Style '{name}' not found")

    delete_style(style.filename)
    await session.execute(delete(Style).where(Style.id == style.id))
    await session.commit()

    return {"message": f"Style '{name}' deleted"}
