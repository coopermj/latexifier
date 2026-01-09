import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..auth import RequireAPIKey

router = APIRouter(prefix="/packages", tags=["packages"])


class PackageInstallRequest(BaseModel):
    packages: list[str] = Field(..., description="List of TeX package names to install")


class PackageInstallResponse(BaseModel):
    success: bool
    installed: list[str]
    failed: list[str]
    log: str


@router.get("", summary="List installed packages")
async def list_packages(_: RequireAPIKey):
    """List installed TeX packages."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "tlmgr", "list", "--only-installed",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        if proc.returncode != 0:
            return {
                "success": False,
                "packages": [],
                "error": stderr.decode()
            }

        # Parse package list
        packages = []
        for line in stdout.decode().split("\n"):
            line = line.strip()
            if line.startswith("i "):
                # Format: "i package-name: description"
                parts = line[2:].split(":", 1)
                if parts:
                    packages.append(parts[0].strip())

        return {
            "success": True,
            "packages": sorted(packages),
            "count": len(packages)
        }

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Package listing timed out")
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="tlmgr not available. TeX Live may not be fully installed."
        )


@router.post("/install", response_model=PackageInstallResponse, summary="Install TeX packages")
async def install_packages(
    request: PackageInstallRequest,
    _: RequireAPIKey
):
    """
    Install additional TeX packages using tlmgr.

    Note: Package installation persists in the container but may be lost on redeployment.
    Consider adding frequently needed packages to the Dockerfile.
    """
    if not request.packages:
        raise HTTPException(status_code=400, detail="No packages specified")

    installed = []
    failed = []
    full_log = []

    for package in request.packages:
        # Sanitize package name
        if not package.replace("-", "").replace("_", "").isalnum():
            failed.append(package)
            full_log.append(f"Invalid package name: {package}")
            continue

        try:
            proc = await asyncio.create_subprocess_exec(
                "tlmgr", "install", package,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            log = stdout.decode()
            full_log.append(f"=== {package} ===\n{log}")

            if proc.returncode == 0:
                installed.append(package)
            else:
                failed.append(package)

        except asyncio.TimeoutError:
            failed.append(package)
            full_log.append(f"=== {package} ===\nInstallation timed out")
        except Exception as e:
            failed.append(package)
            full_log.append(f"=== {package} ===\nError: {str(e)}")

    return PackageInstallResponse(
        success=len(failed) == 0,
        installed=installed,
        failed=failed,
        log="\n\n".join(full_log)
    )
