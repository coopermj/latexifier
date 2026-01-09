import base64
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from ..auth import RequireAPIKey
from ..storage import save_font, delete_font, get_fonts_path
from ..models import FontInfo

router = APIRouter(prefix="/fonts", tags=["fonts"])

VALID_EXTENSIONS = (".ttf", ".otf", ".woff", ".woff2", ".pfb", ".pfm")


@router.get("", response_model=list[FontInfo], summary="List available fonts")
async def list_fonts(_: RequireAPIKey):
    """List all available custom fonts."""
    fonts_path = get_fonts_path()
    fonts = []

    for f in sorted(fonts_path.iterdir()):
        if f.is_file() and f.suffix.lower() in VALID_EXTENSIONS:
            stat = f.stat()
            fonts.append(FontInfo(
                name=f.stem,
                filename=f.name,
                uploaded_at=datetime.fromtimestamp(stat.st_mtime).isoformat()
            ))

    return fonts


@router.post("", response_model=FontInfo, summary="Upload a font file")
async def upload_font(
    _: RequireAPIKey,
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

    if not file_name.lower().endswith(VALID_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Font files must have one of these extensions: {', '.join(VALID_EXTENSIONS)}"
        )

    # Check if already exists
    font_path = get_fonts_path() / file_name
    if font_path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Font '{file_name}' already exists. Delete it first to replace."
        )

    await save_font(file_name, file_content)

    return FontInfo(
        name=name or file_name.rsplit(".", 1)[0],
        filename=file_name,
        uploaded_at=datetime.now().isoformat()
    )


@router.delete("/{name}", summary="Delete a font")
async def remove_font(name: str, _: RequireAPIKey):
    """Delete a custom font by name."""
    fonts_path = get_fonts_path()

    # Find file by name (stem) or exact filename
    found = None
    for f in fonts_path.iterdir():
        if f.stem == name or f.name == name:
            found = f
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Font '{name}' not found")

    delete_font(found.name)
    return {"message": f"Font '{name}' deleted"}
