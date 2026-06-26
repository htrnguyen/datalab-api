"""Schema extraction endpoint for multi-schema structured extraction."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import get_settings
from app.schemas.extraction import ExtractionResponse
from app.services.extraction_client import ExtractionClient
from app.services.extraction_service import ExtractionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/extraction", tags=["extraction"])


_client_initialized = False
_client_init_lock = asyncio.Lock()


async def _get_client() -> ExtractionClient:
    """Get extraction client (singleton per settings), initializing on first call."""
    global _client_initialized
    settings = get_settings()
    client = ExtractionClient(settings)

    if not _client_initialized:
        async with _client_init_lock:
            if not _client_initialized:
                await client.initialize()
                _client_initialized = True

    return client


def _get_service() -> ExtractionService:
    """Get extraction service instance with settings for semaphore."""
    settings = get_settings()
    client = ExtractionClient(settings)
    return ExtractionService(client, settings)


async def _get_service_async() -> ExtractionService:
    """Get extraction service instance with initialized client."""
    settings = get_settings()
    client = await _get_client()
    return ExtractionService(client, settings)


@router.post("", response_model=ExtractionResponse)
async def extract(
    file: UploadFile = File(description="PDF file for extraction"),
    schemas: str = Form(
        description='JSON array of schemas: [{"name":"criteria","schema":"..."},{"name":"bands","schema":"..."}]'
    ),
    name: str | None = Form(default=None, description="Submission ID override"),
) -> ExtractionResponse:
    """
    Extract structured data from a PDF using JSON schemas.

    **schemas format:** JSON array of objects with `name` and `schema` keys.
    ```json
    [
      {"name": "criteria", "schema": "{\"type\":\"object\",...}"},
      {"name": "bands", "schema": "{\"type\":\"object\",...}"}
    ]
    ```

    Multiple schemas run in parallel and results are merged.
    """
    settings = get_settings()
    service = await _get_service_async()
    request_id = uuid.uuid4().hex[:12]

    # Read file
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    filename = file.filename or "upload"

    # Validate file size
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f}MB). Max: {settings.max_upload_size_mb:.0f}MB",
        )

    # Parse schemas
    schema_list = service.parse_schemas_input(schemas)
    if not schema_list:
        raise HTTPException(
            status_code=400,
            detail="Invalid schemas format. Expected: [{\"name\":\"...\",\"schema\":\"...\"}]",
        )

    # Generate submission ID
    submission_id = name or service.extract_submission_id(filename)

    logger.info("[%s] Starting extraction: %s, %d schemas", request_id, filename, len(schema_list))

    # Run extraction(s)
    if len(schema_list) == 1:
        schema_name, schema_content = schema_list[0]
        result = await service.extract_single(
            file_bytes, filename, schema_content, schema_name, request_id
        )
        results = {schema_name: result}
    else:
        results = await service.extract_multi(file_bytes, filename, schema_list, request_id)

    # Aggregate and return
    schema_extraction, markdown, score_avg, errors, schemas_run = service.aggregate_results(results)

    logger.info("[%s] Completed: success=%s, errors=%d", request_id, len(errors) == 0, len(errors))

    return ExtractionResponse(
        success=len(errors) == 0,
        submission_id=submission_id,
        schemas_run=schemas_run,
        schema_extraction=schema_extraction,
        markdown=markdown,
        score_avg=score_avg,
        pages=0,
        extracted_at=datetime.now(timezone.utc).isoformat(),
        errors=errors,
    )
