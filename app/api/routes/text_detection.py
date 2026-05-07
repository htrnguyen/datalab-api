"""PaddleOCRv5 text detection API routes."""

from __future__ import annotations

import asyncio
from typing import Annotated, List

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.text_detection import (
    Detection,
    ImageSize,
    TextDetectionBatchResponse,
    TextDetectionItem,
)
from app.services.paddle_text_det import (
    PaddleTextDetector,
    PaddleTextDetectorError,
)

router = APIRouter(prefix="/api/v1", tags=["text-detection"])


@router.post(
    "/text-detection",
    response_model=TextDetectionBatchResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "files": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "format": "binary",
                                },
                            },
                        },
                        "required": ["files"],
                    }
                }
            },
        }
    },
)
async def detect_text(
    files: Annotated[
        list[UploadFile],
        File(
            ...,
            description="Upload one or more image files.",
        ),
    ],
) -> TextDetectionBatchResponse:
    """Detect text regions on uploaded images using PP-OCRv5."""
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    try:
        detector = PaddleTextDetector.get()
    except PaddleTextDetectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    items: List[TextDetectionItem] = []
    for file in files:
        raw = await file.read()
        if not raw:
            raise HTTPException(
                status_code=400,
                detail=f"Empty file: {file.filename or 'unknown'}",
            )
        name = file.filename or "upload.png"
        try:
            result = await asyncio.to_thread(
                detector.predict_bytes,
                raw,
                name,
            )
        except PaddleTextDetectorError as exc:
            raise HTTPException(
                status_code=503,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Failed to detect {name}: {exc}",
            ) from exc
        items.append(_to_item(name, result))
    return TextDetectionBatchResponse(results=items)


def _to_item(name: str, result: dict) -> TextDetectionItem:
    return TextDetectionItem(
        filename=name,
        image_size=ImageSize(
            width=result["width"],
            height=result["height"],
        ),
        detections=[Detection(**d) for d in result["detections"]],
    )
