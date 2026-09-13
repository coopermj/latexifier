"""Pinned TeX dependencies shared by API and web compilation."""
import shutil
from pathlib import Path


def copy_bundled_tex_assets(work_dir: Path) -> None:
    """Install bundled runtime assets after stored styles to prevent stale copies."""
    for asset in (Path(__file__).parent / "tex").iterdir():
        if asset.is_file() and asset.suffix in {".sty", ".tex", ".otf", ".ttf"}:
            shutil.copy2(asset, work_dir / asset.name)
