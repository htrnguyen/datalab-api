"""File storage endpoints for serving cropped images."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/v1/files", tags=["files"])

STORAGE_DIR = Path("uploads")


@router.get("/{file_id}", summary="Get image")
async def get_file(file_id: str) -> FileResponse:
    """Retrieve image by file_id.

    Images are cropped from OCR processing and stored in uploads/.
    """
    file_path = STORAGE_DIR / f"{file_id}.png"

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(
        path=file_path,
        media_type="image/png",
        filename=f"{file_id}.png",
    )
