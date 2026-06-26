"""Pydantic models for extraction endpoint."""
from __future__ import annotations

from typing import Annotated

from fastapi import File, Form
from pydantic import BaseModel


class SchemaInput(BaseModel):
    """Single schema input for extraction."""

    name: str = "default"
    schema_json: str


class ExtractionResponse(BaseModel):
    """Response model for extraction endpoint."""

    success: bool = True
    submission_id: str
    schemas_run: list[str]
    schema_extraction: dict
    markdown: str = ""
    score_avg: float | None = None
    pages: int = 0
    extracted_at: str
    errors: dict = {}


class ExtractionResult(BaseModel):
    """Result from a single schema extraction."""

    schema_name: str
    data: dict
    markdown: str = ""
    score_avg: float | None = None
    status: str | None = None
    error: str | None = None
