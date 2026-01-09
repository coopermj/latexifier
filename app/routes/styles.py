import base64
from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from ..auth import RequireAPIKey
from ..database import is_db_available, get_session, Style
from ..storage import save_style, delete_style, list_styles as list_style_files
from ..models import StyleInfo

router = APIRouter(prefix="/styles", tags=["styles"])


def require_db():
    if not is_db_available():
        raise HTTPException(
            status_code=503,
            detail="Database not available. Style management requires database."
        )


@router.get("", response_model=list[StyleInfo], summary="List available styles")
async def list_styles(_: RequireAPIKey):
    """List all available custom LaTeX style files."""
    require_db()

    from sqlalchemy import select

    async for session in get_session():
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
    file: UploadFile | None = File(None),
    name: str | None = Form(None),
    content: str | None = Form(None),
    filename: str | None = Form(None)
):
    """
    Upload a custom LaTeX style file (.sty or .cls).

    Either upload a file directly or provide base64-encoded content.
    """
    require_db()

    from sqlalchemy import select

    if file:
        file_content = await file.read()
        file_name = file.filename
        style_name = name or file_name.rsplit(".", 1)[0]
    elif content and filename:
        file_content = base64.b64decode(content)
        file_name = filename
        style_name = name or filename.rsplit(".", 1)[0]
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either a file upload or content+filename"
        )

    if not file_name.endswith((".sty", ".cls", ".tex")):
        raise HTTPException(
            status_code=400,
            detail="Style files must have .sty, .cls, or .tex extension"
        )

    async for session in get_session():
        existing = await session.execute(
            select(Style).where(Style.name == style_name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Style '{style_name}' already exists. Delete it first to replace."
            )

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
async def remove_style(name: str, _: RequireAPIKey):
    """Delete a custom style by name."""
    require_db()

    from sqlalchemy import select, delete

    async for session in get_session():
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
