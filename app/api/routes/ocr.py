"""OCR API routes."""

from __future__ import annotations

from copy import deepcopy
from typing import Annotated
from typing import Any
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.pipeline import process_image_bytes
from app.schemas.ocr import OcrBatchResponse, OcrItemResponse
from app.services.html_clean import html_to_text

router = APIRouter(prefix="/api/v1", tags=["ocr"])


def _clean_nodes_for_output(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace raw html field with plain text recursively."""
    cleaned: list[dict[str, Any]] = []
    for node in nodes:
        item = deepcopy(node)
        html = item.get("html")
        if isinstance(html, str):
            item["text"] = html_to_text(html)
            item.pop("html", None)
        children = item.get("children")
        if isinstance(children, list):
            item["children"] = _clean_nodes_for_output(children)
        cleaned.append(item)
    return cleaned


@router.post(
    "/ocr",
    response_model=OcrBatchResponse,
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
                            "refine": {
                                "type": "boolean",
                                "default": True,
                            },
                        },
                        "required": ["files"],
                    }
                }
            },
        }
    },
)
async def ocr_images(
    files: Annotated[
        list[UploadFile],
        File(
            ...,
            description="Upload one or more image files.",
        ),
    ],
    refine: Annotated[
        bool,
        Form(
            description="Enable recursive infographic refinement.",
        ),
    ] = True,
) -> OcrBatchResponse:
    """Run OCR pipeline on uploaded images."""
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    items: List[OcrItemResponse] = []
    for file in files:
        raw = await file.read()
        if not raw:
            raise HTTPException(
                status_code=400,
                detail=f"Empty file: {file.filename or 'unknown'}",
            )
        name = file.filename or "upload.png"
        try:
            result = process_image_bytes(raw, name, refine=refine)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Failed to process {name}: {exc}",
            ) from exc
        items.append(
            OcrItemResponse(
                filename=name,
                children=_clean_nodes_for_output(
                    result.get("children", []),
                ),
                metadata=result.get("metadata"),
            )
        )
    return OcrBatchResponse(results=items)
