"""OCR service - handles Datalab API calls and response transformation."""

from __future__ import annotations

import copy
import io
import json
import logging
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.config import get_settings
from app.schemas.ocr import (
    BlockContent,
    OCRResponse,
    PageResult,
    Polygon,
)
from app.services.datalab_client import DatalabClient
from app.services.html_clean import html_to_text

logger = logging.getLogger(__name__)


class OCRService:
    """Service for OCR processing via Datalab API."""

    def __init__(self, datalab_client: DatalabClient):
        self._client = datalab_client

    def process(
        self,
        file_bytes: bytes,
        filename: str,
        mode: str = "accurate",
        infographic: bool = False,
        request_id: str | None = None,
    ) -> OCRResponse:
        """Process file through Datalab API and return unified response.

        Args:
            file_bytes: Raw file content
            filename: Original filename
            mode: Processing mode (fast, balanced, accurate)
            infographic: Extract table structure with line-by-line breakdown
            request_id: Optional request ID for tracing
        """
        settings = get_settings()
        size_bytes = len(file_bytes)
        size_mb = size_bytes / (1024 * 1024)

        logger.info(
            "ocr_process_start request_id=%s filename=%s size_bytes=%s size_mb=%.3f mode=%s infographic=%s",
            request_id,
            filename,
            size_bytes,
            size_mb,
            mode,
            infographic,
        )

        start = time.perf_counter()
        try:
            result = self._client.convert(
                file_bytes=file_bytes,
                filename=filename,
                mode=mode,
                output_format="json",
                extras="infographic" if infographic else None,
                mime=None,
            )
        except Exception as exc:
            logger.exception(
                "ocr_datalab_failed request_id=%s filename=%s size_bytes=%s mode=%s infographic=%s",
                request_id,
                filename,
                size_bytes,
                mode,
                infographic,
            )
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "ocr_datalab_done request_id=%s filename=%s size_bytes=%s mode=%s infographic=%s elapsed_ms=%.2f",
            request_id,
            filename,
            size_bytes,
            mode,
            infographic,
            elapsed_ms,
        )

        try:
            response = self._transform_response(result, file_bytes)
        except Exception as exc:
            logger.exception(
                "ocr_transform_failed request_id=%s filename=%s size_bytes=%s mode=%s infographic=%s",
                request_id,
                filename,
                size_bytes,
                mode,
                infographic,
            )
            raise

        block_type_stats = Counter(
            block.block_type for page in response.pages for block in page.blocks
        )
        orig_width = orig_height = 0
        if file_bytes:
            try:
                orig_width, orig_height = Image.open(io.BytesIO(file_bytes)).size
            except Exception as exc:
                logger.debug("ocr_orig_image_size_failed error=%s", exc)
        page_sizes = [
            f"{page.width}x{page.height}" for page in response.pages
        ] or ["0x0"]
        logger.info(
            "ocr_transform_done request_id=%s filename=%s size_bytes=%s page_count=%s block_count=%s block_types=%s runtime_seconds=%s cost_cents=%s orig_size=%s page_sizes=%s",
            request_id,
            filename,
            size_bytes,
            response.page_count,
            sum(len(page.blocks) for page in response.pages),
            dict(block_type_stats),
            response.runtime_seconds,
            response.cost_cents,
            f"{orig_width}x{orig_height}",
            page_sizes,
        )

        if settings.debug_log_enabled:
            try:
                self._save_debug_payload(
                    request_id=request_id,
                    filename=filename,
                    mode=mode,
                    infographic=infographic,
                    datalab_result=result,
                    response=response,
                )
            except Exception as exc:  # pragma: no cover - best-effort debug
                logger.debug("ocr_debug_save_failed request_id=%s: %s", request_id, exc)

        return response

    def _save_debug_payload(
        self,
        request_id: str | None,
        filename: str,
        mode: str,
        infographic: bool,
        datalab_result: dict[str, Any],
        response: OCRResponse,
    ) -> None:
        if not get_settings().debug_save_response:
            return

        debug_dir = get_settings().debug_dir
        debug_dir.mkdir(exist_ok=True, parents=True)

        payload = {
            "request": {
                "request_id": request_id,
                "filename": filename,
                "mode": mode,
                "infographic": infographic,
            },
            "datalab_result": datalab_result,
            "endpoint_response": json.loads(response.model_dump_json()),
        }

        safe_name = Path(filename or "upload").name or "upload"
        stem = Path(safe_name).stem
        suffix = Path(safe_name).suffix or ".bin"
        ts = time.strftime("%Y%m%d_%H%M%S")
        req_prefix = f"{request_id}_" if request_id else ""
        file_name = f"debug_{ts}_{req_prefix}{stem}_{mode}{suffix}.json"
        target = debug_dir / file_name

        with target.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

        logger.info("ocr_debug_saved request_id=%s path=%s", request_id, target)

    def _transform_response(
        self,
        datalab_result: dict[str, Any],
        source_bytes: bytes | None = None,
    ) -> OCRResponse:
        """Transform Datalab response to unified OCRResponse schema."""
        json_tree = datalab_result.get("json", {})
        children = json_tree.get("children", [])

        # Find page nodes
        page_nodes = [c for c in children if c.get("block_type") == "Page"]

        # Read original image dimensions from source bytes for coordinate transform
        orig_w, orig_h = 0, 0
        if source_bytes:
            try:
                img = Image.open(io.BytesIO(source_bytes))
                orig_w, orig_h = img.size
            except Exception as exc:
                logger.debug("ocr_source_image_read_failed error=%s", exc)

        pages: list[PageResult] = []
        block_counter = 0

        if not page_nodes:
            # No page wrapper, use defaults
            page_width = 0
            page_height = 0
            blocks = self._extract_blocks(
                children,
                page_idx=0,
                counter_start=0,
                source_bytes=source_bytes,
                page_width=page_width,
                page_height=page_height,
                orig_w=orig_w,
                orig_h=orig_h,
            )
            pages.append(PageResult(page_index=0, blocks=blocks))
        else:
            for page_idx, page_node in enumerate(page_nodes):
                bbox = page_node.get("bbox", [])
                page_width = max(0, int(bbox[2]) - int(bbox[0])) if len(bbox) >= 3 else 0
                page_height = max(0, int(bbox[3]) - int(bbox[1])) if len(bbox) >= 4 else 0

                logger.debug(
                    "ocr_page page_index=%s page_width=%s page_height=%s orig_width=%s orig_height=%s",
                    page_idx,
                    page_width,
                    page_height,
                    orig_w,
                    orig_h,
                )

                page_children = page_node.get("children", [])
                start_counter = block_counter
                blocks = self._extract_blocks(
                    page_children,
                    page_idx=page_idx,
                    counter_start=start_counter,
                    source_bytes=source_bytes,
                    page_width=page_width,
                    page_height=page_height,
                    orig_w=orig_w,
                    orig_h=orig_h,
                )
                block_counter = start_counter + len(blocks)

                pages.append(
                    PageResult(
                        page_index=page_idx,
                        width=page_width,
                        height=page_height,
                        blocks=blocks,
                    )
                )

        # Extract cost info
        cost_data = datalab_result.get("cost_breakdown") or {}

        # Remove base64 images from raw response to reduce size
        raw_response = self._strip_base64(datalab_result)

        response = OCRResponse(
            success=datalab_result.get("success", True),
            page_count=datalab_result.get("page_count", len(pages)),
            pages=pages,
            runtime_seconds=datalab_result.get("runtime"),
            cost_cents=cost_data.get("final_cost_cents"),
            raw=raw_response,
        )

        logger.debug(
            "ocr_transform_summary page_count=%s block_count=%s raw_keys=%s",
            response.page_count,
            sum(len(page.blocks) for page in response.pages),
            sorted((response.raw or {}).keys())[:20],
        )

        return response

    def _strip_base64(self, data: dict[str, Any]) -> dict[str, Any]:
        """Clean raw response - remove base64, metadata thừa."""
        result = copy.deepcopy(data)

        # Fields to remove from top level
        result.pop("images", None)
        result.pop("markdown", None)
        result.pop("html", None)
        result.pop("extraction_schema_json", None)
        result.pop("extraction_score_average", None)
        result.pop("extraction_mode", None)
        result.pop("segmentation_results", None)
        result.pop("parse_quality_score", None)
        result.pop("checkpoint_id", None)
        result.pop("versions", None)
        result.pop("evaluation", None)

        # Clean nested nodes
        def strip_node(node: dict):
            node.pop("images", None)
            node.pop("markdown", None)
            node.pop("page", None)
            node.pop("section_hierarchy", None)
            node.pop("inference_failed", None)
            node.pop("metadata", None)
            node.pop("bbox", None)
            if "children" in node:
                for child in node["children"]:
                    strip_node(child)

        if "json" in result:
            strip_node(result["json"])

        result.pop("metadata", None)
        result.pop("cost_breakdown", None)
        result.pop("result_url", None)
        result.pop("expires_in", None)
        result.pop("chunks", None)
        result.pop("status", None)
        result.pop("output_format", None)
        result.pop("page_count", None)
        result.pop("total_cost", None)
        result.pop("runtime", None)

        return result

    def _extract_blocks(
        self,
        nodes: list[dict[str, Any]],
        page_idx: int,
        counter_start: int,
        source_bytes: bytes | None = None,
        page_width: int = 0,
        page_height: int = 0,
        orig_w: int = 0,
        orig_h: int = 0,
    ) -> list[BlockContent]:
        """Extract blocks from Datalab tree structure."""
        blocks: list[BlockContent] = []
        counter = counter_start

        for node in nodes:
            block_type = node.get("block_type", "")
            block_id = node.get("id", f"p{page_idx}_b{counter}")

            if block_type == "Page":
                continue

            unified_type = self._map_block_type(block_type)

            text = ""
            html = node.get("html") or ""

            if block_type == "Text":
                text = node.get("text") or ""
                if not text:
                    text = html_to_text(html)
            else:
                text = html_to_text(html)

            polygon_list = node.get("polygon")
            bbox_list = node.get("bbox", [])

            polygon: Polygon | None = None
            if polygon_list and isinstance(polygon_list, list):
                polygon = Polygon(points=polygon_list)
            elif bbox_list and len(bbox_list) == 4:
                polygon = Polygon(
                    points=[
                        [bbox_list[0], bbox_list[1]],
                        [bbox_list[2], bbox_list[1]],
                        [bbox_list[2], bbox_list[3]],
                        [bbox_list[0], bbox_list[3]],
                    ]
                )

            scale_x = 1.0
            scale_y = 1.0
            if polygon and orig_w and orig_h:
                scale_x = orig_w / page_width if page_width else 1.0
                scale_y = orig_h / page_height if page_height else 1.0
                rotation = node.get("rotation") or 0
                transformed_points = _transform_polygon_points(
                    polygon_list=list(polygon.points),
                    bbox_list=bbox_list,
                    scale_x=scale_x,
                    scale_y=scale_y,
                    rotation=rotation,
                    orig_w=orig_w,
                    orig_h=orig_h,
                )
                polygon = Polygon(points=transformed_points)

            block = BlockContent(
                id=block_id,
                block_type=unified_type,
                content=text.strip() if text else "",
                html=html if html else None,
                polygon=polygon,
                confidence=node.get("confidence", 1.0),
            )
            blocks.append(block)

            logger.debug(
                "ocr_block page=%s id=%s type=%s text_len=%s polygon=%s scale=%.4f,%.4f",
                page_idx,
                block_id,
                unified_type,
                len(block.content),
                [round(x, 2) for x in (polygon.points[0] + polygon.points[2])]
                if polygon and polygon.points
                else None,
                scale_x,
                scale_y,
            )

            counter += 1

            # Recursively process children (don't increment counter for children blocks)
            for child in node.get("children", []):
                child_blocks = self._extract_blocks(
                    [child],
                    page_idx=page_idx,
                    counter_start=counter,
                    source_bytes=source_bytes,
                    page_width=page_width,
                    page_height=page_height,
                    orig_w=orig_w,
                    orig_h=orig_h,
                )
                blocks.extend(child_blocks)
                counter += len(child_blocks)

        return blocks

    def _map_block_type(self, datalab_type: str) -> str:
        """Map Datalab block type to unified type."""
        type_mapping = {
            "Text": "text",
            "Table": "table",
            "Figure": "figure",
            "Picture": "figure",
            "Image": "figure",
            "ListGroup": "list",
            "ListItem": "list",
            "PageHeader": "header",
            "PageFooter": "page_footer",
            "Header": "header",
            "Footer": "footer",
            "Title": "title",
            "SectionHeader": "text",
        }
        return type_mapping.get(datalab_type, "text")


def _transform_polygon_points(
    *,
    polygon_list: list[Any] | None,
    bbox_list: list[Any],
    scale_x: float,
    scale_y: float,
    rotation: float,
    orig_w: float,
    orig_h: float,
) -> list[list[float]]:
    base_points = polygon_list if polygon_list is not None else [
        [bbox_list[0], bbox_list[1]],
        [bbox_list[2], bbox_list[1]],
        [bbox_list[2], bbox_list[3]],
        [bbox_list[0], bbox_list[3]],
    ]

    if not rotation and scale_x == 1.0 and scale_y == 1.0:
        return [list(point) for point in base_points]

    radians = math.radians(rotation % 360)
    sin_r, cos_r = math.sin(radians), math.cos(radians)

    center_x = orig_w / 2 if orig_w else 0.0
    center_y = orig_h / 2 if orig_h else 0.0

    transformed: list[list[float]] = []
    for x, y in base_points:
        sx = x * scale_x
        sy = y * scale_y
        dx = sx - center_x
        dy = sy - center_y
        rx = dx * cos_r - dy * sin_r
        ry = dx * sin_r + dy * cos_r
        transformed.append([rx + center_x, ry + center_y])

    return transformed
