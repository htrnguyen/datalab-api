"""Extraction service - business logic layer."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from app.schemas.extraction import ExtractionResult

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.services.extraction_client import ExtractionClient

logger = logging.getLogger(__name__)


class ExtractionService:
    """Service layer for extraction operations.

    Handles:
    - Single schema extraction
    - Multi-schema parallel extraction (with semaphore rate limiting)
    - Result aggregation
    """

    def __init__(self, client: ExtractionClient, settings: Settings | None = None):
        self._client = client
        self._semaphore: asyncio.Semaphore | None = None
        if settings:
            self._semaphore = asyncio.Semaphore(settings.max_concurrent_requests)

    def _generate_request_id(self, filename: str) -> str:
        """Generate unique request ID for tracking."""
        stem = Path(filename).stem[:16]
        short_uuid = uuid.uuid4().hex[:8]
        return f"{stem}_{short_uuid}"

    @staticmethod
    def extract_submission_id(path: str) -> str:
        """Extract a short submission ID from a filename."""
        stem = Path(path).stem
        parts = re.split(r"[_\-]", stem)
        for part in reversed(parts):
            part = part.strip()
            if re.match(r"^[a-zA-Z0-9]+$", part) and len(part) <= 20:
                return part
        safe = re.sub(r"[^a-zA-Z0-9]", "_", stem).strip("_")
        return safe[:20]

    async def extract_single(
        self,
        file_bytes: bytes,
        filename: str,
        schema_json: str,
        schema_name: str = "default",
        request_id: str | None = None,
    ) -> ExtractionResult:
        """Run single schema extraction.

        Args:
            file_bytes: File content
            filename: Original filename
            schema_json: JSON schema string
            schema_name: Schema identifier
            request_id: Optional request ID for tracking

        Returns:
            ExtractionResult with parsed data
        """
        req_id = request_id or self._generate_request_id(filename)

        try:
            result = await self._client.submit_and_poll(
                file_bytes, filename, schema_json, schema_name, req_id
            )
            raw = json.loads(result.get("extraction_schema_json", "{}"))

            return ExtractionResult(
                schema_name=schema_name,
                data=raw,
                markdown=result.get("markdown", ""),
                score_avg=result.get("_score_avg"),
                status=result.get("status"),
            )
        except Exception as e:
            logger.error("[%s/%s] Extraction failed: %s", req_id, schema_name, e)
            return ExtractionResult(
                schema_name=schema_name,
                data={},
                error=str(e),
            )

    async def extract_multi(
        self,
        file_bytes: bytes,
        filename: str,
        schema_list: list[tuple[str, str]],
        request_id: str | None = None,
    ) -> dict[str, ExtractionResult]:
        """Run multiple schemas in parallel with rate limiting.

        Args:
            file_bytes: File content
            filename: Original filename
            schema_list: List of (schema_name, schema_json) tuples
            request_id: Optional request ID for tracking

        Returns:
            Dict mapping schema names to results
        """
        req_id = request_id or self._generate_request_id(filename)
        logger.info("[%s] Running %d schemas in parallel", req_id, len(schema_list))

        results: dict[str, ExtractionResult] = {}
        tasks = []

        for name, schema_json in schema_list:
            coro = self._run_with_semaphore(
                file_bytes, filename, schema_json, name, req_id
            )
            tasks.append(coro)

        for coro in asyncio.as_completed(tasks):
            result = await coro
            results[result.schema_name] = result
            if result.error:
                logger.error("[%s/%s] ERROR: %s", req_id, result.schema_name, result.error)
            else:
                logger.info("[%s/%s] Done", req_id, result.schema_name)

        return results

    async def _run_with_semaphore(
        self,
        file_bytes: bytes,
        filename: str,
        schema_json: str,
        schema_name: str,
        request_id: str,
    ) -> ExtractionResult:
        """Run extraction with semaphore rate limiting."""
        if self._semaphore is not None:
            async with self._semaphore:
                return await self.extract_single(
                    file_bytes, filename, schema_json, schema_name, request_id
                )
        return await self.extract_single(
            file_bytes, filename, schema_json, schema_name, request_id
        )

    @staticmethod
    def parse_schemas_input(
        schemas_json: str | None,
    ) -> list[tuple[str, str]]:
        """Parse schemas form input into list of (name, json) tuples.

        Args:
            schemas_json: JSON array of {name, schema} objects

        Returns:
            List of (name, schema_json) tuples
        """
        if not schemas_json:
            return []

        try:
            items = json.loads(schemas_json)
            if not isinstance(items, list):
                return []
            return [
                (item.get("name", f"schema_{i}"), item.get("schema", ""))
                for i, item in enumerate(items)
                if isinstance(item, dict) and item.get("schema")
            ]
        except json.JSONDecodeError:
            return []

    @staticmethod
    def aggregate_results(
        results: dict[str, ExtractionResult],
    ) -> tuple[dict, str, float | None, dict[str, str], list[str]]:
        """Aggregate multiple extraction results.

        Args:
            results: Dict of schema_name -> ExtractionResult

        Returns:
            Tuple of (schema_extraction, markdown, score_avg, errors, schemas_run)
        """
        primary_md = ""
        schema_extraction: dict = {}
        score_avg: float | None = None
        errors: dict[str, str] = {}
        schemas_run: list[str] = []

        for schema_key, result in results.items():
            schemas_run.append(schema_key)

            if result.error:
                errors[schema_key] = result.error
                continue

            if result.markdown and not primary_md:
                primary_md = result.markdown
            if result.score_avg is not None and score_avg is None:
                score_avg = result.score_avg

            for top_key, top_val in result.data.items():
                schema_extraction[top_key] = top_val

        return schema_extraction, primary_md, score_avg, errors, schemas_run
