from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Polygon(BaseModel):
    points: list[list[float]]


class BlockContent(BaseModel):
    id: str
    block_type: str
    content: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    polygon: Polygon | None = None
    html: str | None = None


class PageResult(BaseModel):
    page_index: int = Field(ge=0)
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)
    blocks: list[BlockContent] = Field(default_factory=list)


class OCRResponse(BaseModel):
    success: bool = True
    page_count: int = Field(default=0, ge=0)
    pages: list[PageResult] = Field(default_factory=list)
    runtime_seconds: float | None = Field(default=None)
    cost_cents: float | None = Field(default=None)
    raw: dict[str, Any] | None = Field(default=None)
