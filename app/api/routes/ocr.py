"""OCR API routes."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.core.config import get_settings
from app.schemas.ocr import OCRResponse
from app.services.datalab_client import DatalabClient
from app.services.ocr_service import OCRService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ocr", tags=["ocr"])

VALID_MODES = {"fast", "balanced", "accurate"}


@lru_cache
def _get_client() -> DatalabClient:
    """Cached client instance for connection reuse."""
    return DatalabClient()


@lru_cache
def _get_service() -> OCRService:
    """Cached service instance."""
    return OCRService(_get_client())


def get_ocr_service() -> OCRService:
    """Dependency for OCR service."""
    return _get_service()


@router.post("", summary="Process OCR", response_model=OCRResponse)
async def process_ocr(
    file: Annotated[UploadFile, File(description="Image (PNG, JPG, WEBP) or PDF file")],
    mode: Annotated[
        str,
        Query(description="Processing mode: fast, balanced, or accurate"),
    ] = "accurate",
    infographic: Annotated[
        bool,
        Query(description="Extract table structure with line-by-line breakdown"),
    ] = False,
    service: OCRService = Depends(get_ocr_service),
) -> OCRResponse:
    """Process OCR on uploaded file.

    Returns unified OCR response with normalized structure:
    - Text blocks with content, bbox/polygon, confidence
    - Table blocks with HTML content
    - Figure blocks with cropped images from bbox
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")

    size_mb = len(raw) / (1024 * 1024)
    if size_mb > get_settings().max_upload_size_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f}MB). Max: {get_settings().max_upload_size_mb:.0f}MB",
        )

    if mode not in VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {mode}. Must be one of: {', '.join(VALID_MODES)}",
        )

    try:
        result = service.process(
            file_bytes=raw,
            filename=file.filename or "upload",
            mode=mode,
            infographic=infographic,
        )
        return result

    except Exception as exc:
        logger.exception("OCR processing failed")
        raise HTTPException(status_code=500, detail=str(exc))
