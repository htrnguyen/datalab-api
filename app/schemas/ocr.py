"""OCR API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Polygon(BaseModel):
    """Polygon coordinates as list of [x, y] points."""
    points: list[list[float]]

    @classmethod
    def from_list(cls, points: list[list[float]]) -> Polygon:
        return cls(points=points)

    def to_list(self) -> list[list[float]]:
        return self.points


class ImageRef(BaseModel):
    """Reference to extracted/cropped image stored in uploads."""
    file_id: str = Field(description="File ID for GET /api/v1/files/{file_id}")
    url: str | None = Field(default=None, description="Full URL to retrieve image")
    description: str = Field(default="", description="Image description or alt text")
    caption: str | None = Field(default=None, description="Image caption if available")
    width: int | None = Field(default=None, description="Image width in pixels")
    height: int | None = Field(default=None, description="Image height in pixels")

    def with_base_url(self, base_url: str) -> ImageRef:
        """Add base URL to image reference."""
        if self.url is None and self.file_id:
            self.url = f"{base_url.rstrip('/')}/api/v1/files/{self.file_id}"
        return self


class BlockContent(BaseModel):
    """OCR content block."""
    id: str = Field(description="Unique block identifier")
    block_type: str = Field(
        default="text",
        description="Block type: text, table, figure, page_footer, header, list"
    )
    content: str = Field(default="", description="Raw text content (HTML stripped)")
    html: str | None = Field(default=None, description="Original HTML content")
    polygon: Polygon | None = Field(default=None, description="Polygon coordinates")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reading_order: int = Field(default=0, ge=0)
    language: str | None = Field(default=None, description="Detected language")
    image: ImageRef | None = Field(default=None, description="Image reference (only for figures)")

    class Config:
        populate_by_name = True


class PageResult(BaseModel):
    """OCR result for a single page."""
    page_index: int = Field(ge=0)
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)
    blocks: list[BlockContent] = Field(default_factory=list)


class CostBreakdown(BaseModel):
    """Cost information from Datalab."""
    final_cost_cents: int | None = None
    list_cost_cents: int | None = None
    regional_multiplier: int | None = None

    @classmethod
    def from_datalab(cls, data: dict[str, Any] | None) -> CostBreakdown:
        if not data:
            return cls()
        return cls(
            final_cost_cents=data.get("final_cost_cents"),
            list_cost_cents=data.get("list_cost_cents"),
            regional_multiplier=data.get("regional_multiplier"),
        )


class OCRResponse(BaseModel):
    """Unified OCR response schema."""
    success: bool = True
    page_count: int = Field(default=0, ge=0)
    pages: list[PageResult] = Field(default_factory=list)
    runtime_seconds: float | None = None
    cost: CostBreakdown | None = None
    raw: dict[str, Any] | None = Field(default=None, description="Raw Datalab response")

    class Config:
        populate_by_name = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result = self.model_dump(exclude_none=True)
        if self.raw:
            result["raw"] = self.raw
        return result
