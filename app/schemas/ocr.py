"""Request and response schemas for OCR API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OcrItemResponse(BaseModel):
    """OCR output for one input file."""

    filename: str = Field(description="Original uploaded filename.")
    children: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Datalab JSON tree children after cleanup/refine.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Metadata returned from Datalab convert.",
    )


class OcrBatchResponse(BaseModel):
    """OCR output for one or multiple files."""

    results: List[OcrItemResponse] = Field(
        default_factory=list,
        description="OCR result items in same order as uploaded files.",
    )
