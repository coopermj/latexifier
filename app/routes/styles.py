import base64
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from ..auth import RequireAPIKey
from ..storage import save_style, delete_style, get_styles_path
from ..models import StyleInfo

router = APIRouter(prefix="/styles", tags=["styles"])


@router.get("", response_model=list[StyleInfo], summary="List available styles")
async def list_styles(_: RequireAPIKey):
    """List all available custom LaTeX style files."""
    styles_path = get_styles_path()
    styles = []

    for f in sorted(styles_path.iterdir()):
        if f.is_file() and f.suffix in (".sty", ".cls", ".tex"):
            stat = f.stat()
            styles.append(StyleInfo(
                name=f.stem,
                filename=f.name,
                uploaded_at=datetime.fromtimestamp(stat.st_mtime).isoformat()
            ))

    return styles


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
    if file:
        file_content = await file.read()
        file_name = file.filename
    elif content and filename:
        file_content = base64.b64decode(content)
        file_name = filename
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

    # Check if already exists
    style_path = get_styles_path() / file_name
    if style_path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Style '{file_name}' already exists. Delete it first to replace."
        )

    await save_style(file_name, file_content)

    return StyleInfo(
        name=name or file_name.rsplit(".", 1)[0],
        filename=file_name,
        uploaded_at=datetime.now().isoformat()
    )


@router.delete("/{name}", summary="Delete a style")
async def remove_style(name: str, _: RequireAPIKey):
    """Delete a custom style by name."""
    styles_path = get_styles_path()

    # Find file by name (stem) or exact filename
    found = None
    for f in styles_path.iterdir():
        if f.stem == name or f.name == name:
            found = f
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Style '{name}' not found")

    delete_style(found.name)
    return {"message": f"Style '{name}' deleted"}
