import asyncio
import base64
import os
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

from .config import get_settings
from .models import CompileRequest, FileItem, TexEngine


class CompilationError(Exception):
    def __init__(self, message: str, log: str = ""):
        self.message = message
        self.log = log
        super().__init__(message)


async def check_latex_available() -> tuple[bool, str | None]:
    """Check if pdflatex is available and return version."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "pdflatex", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            version = stdout.decode().split("\n")[0]
            return True, version
        return False, None
    except FileNotFoundError:
        return False, None


async def compile_latex(request: CompileRequest) -> tuple[bytes, str]:
    """
    Compile LaTeX to PDF.

    Returns: (pdf_bytes, log_output)
    Raises: CompilationError on failure
    """
    settings = get_settings()
    work_dir = Path(tempfile.mkdtemp(prefix="latexgen_"))

    try:
        # Set up files in work directory
        if request.content:
            # Single file mode
            tex_content = base64.b64decode(request.content)
            tex_file = work_dir / request.filename
            tex_file.write_bytes(tex_content)
            main_file = request.filename
        elif request.files:
            # Multi-file mode
            for file_item in request.files:
                file_content = base64.b64decode(file_item.content)
                file_path = work_dir / file_item.name
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(file_content)
            main_file = request.main_file
        elif request.zip:
            # ZIP archive mode
            zip_data = base64.b64decode(request.zip)
            zip_path = work_dir / "archive.zip"
            zip_path.write_bytes(zip_data)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(work_dir)
            zip_path.unlink()
            main_file = request.main_file
        else:
            raise CompilationError("No input provided. Supply content, files, or zip.")

        # Verify main file exists
        main_path = work_dir / main_file
        if not main_path.exists():
            raise CompilationError(f"Main file '{main_file}' not found")

        # Copy global styles and fonts if they exist
        styles_dir = Path(settings.storage_path) / "styles"
        fonts_dir = Path(settings.storage_path) / "fonts"

        if styles_dir.exists():
            for style_file in styles_dir.glob("*"):
                shutil.copy(style_file, work_dir / style_file.name)

        if fonts_dir.exists():
            for font_file in fonts_dir.glob("*"):
                shutil.copy(font_file, work_dir / font_file.name)

        # Select engine
        engine = request.engine.value  # pdflatex, xelatex, or lualatex

        # Run compiler (twice for references)
        log_output = ""
        for run in range(2):
            proc = await asyncio.create_subprocess_exec(
                engine,
                "-interaction=nonstopmode",
                "-halt-on-error",
                main_file,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "TEXMFHOME": str(work_dir)}
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=120  # 2 minute timeout
            )
            log_output = stdout.decode(errors="replace")

            if proc.returncode != 0:
                raise CompilationError(
                    f"LaTeX compilation failed (run {run + 1})",
                    log=log_output
                )

        # Read output PDF
        pdf_name = main_file.rsplit(".", 1)[0] + ".pdf"
        pdf_path = work_dir / pdf_name

        if not pdf_path.exists():
            raise CompilationError("PDF was not generated", log=log_output)

        pdf_bytes = pdf_path.read_bytes()
        return pdf_bytes, log_output

    except asyncio.TimeoutError:
        raise CompilationError("Compilation timed out (120s limit)")
    finally:
        # Clean up work directory
        shutil.rmtree(work_dir, ignore_errors=True)
