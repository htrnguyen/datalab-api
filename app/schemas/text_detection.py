"""Schemas for PaddleOCRv5 text detection endpoint."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class ImageSize(BaseModel):
    """Pixel dimensions of an input image."""

    width: int = Field(description="Input image width in pixels.")
    height: int = Field(description="Input image height in pixels.")


class Detection(BaseModel):
    """Single detected text region."""

    polygon: List[List[int]] = Field(
        description="Polygon as list of [x, y] integer pairs.",
    )
    bbox: List[int] = Field(
        description="Axis-aligned bbox [xmin, ymin, xmax, ymax].",
        min_length=4,
        max_length=4,
    )
    score: float = Field(
        description="Detection confidence in range [0, 1].",
    )


class TextDetectionItem(BaseModel):
    """Detection result for a single image file."""

    filename: str = Field(description="Original uploaded filename.")
    image_size: ImageSize = Field(description="Input image size.")
    detections: List[Detection] = Field(
        default_factory=list,
        description="Detected text regions for the image.",
    )


class TextDetectionBatchResponse(BaseModel):
    """Detection results for one or many uploaded images."""

    results: List[TextDetectionItem] = Field(
        default_factory=list,
        description="Items in the same order as uploaded files.",
    )
