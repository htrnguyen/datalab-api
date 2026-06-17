"""OCR service - handles Datalab API calls and response transformation."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from PIL import Image

from app.schemas.ocr import (
    BlockContent,
    CostBreakdown,
    ImageRef,
    OCRResponse,
    PageResult,
    Polygon,
)
from app.services.datalab_client import DatalabClient
from app.services.html_clean import html_to_text

logger = logging.getLogger(__name__)

STORAGE_DIR = Path("uploads")


class ImageStore:
    """Simple image storage for cropped images."""

    def __init__(self, storage_dir: Path | None = None):
        self._storage_dir = storage_dir or STORAGE_DIR
        self._storage_dir.mkdir(exist_ok=True, parents=True)

    def save(self, image_bytes: bytes, prefix: str = "img") -> str:
        """Save image bytes and return file_id."""
        import hashlib
        import uuid

        file_id = f"{prefix}_{hashlib.md5(image_bytes[:1024]).hexdigest()[:8]}_{uuid.uuid4().hex[:6]}"
        file_path = self._storage_dir / f"{file_id}.png"

        with open(file_path, "wb") as f:
            f.write(image_bytes)

        return file_id


# Global image store
_image_store: ImageStore | None = None


def get_image_store() -> ImageStore:
    """Get or create image store."""
    global _image_store
    if _image_store is None:
        _image_store = ImageStore()
    return _image_store


class OCRService:
    """Service for OCR processing via Datalab API."""

    def __init__(
        self, datalab_client: DatalabClient, image_store: ImageStore | None = None
    ):
        self._client = datalab_client
        self._image_store = image_store or get_image_store()

    def process(
        self,
        file_bytes: bytes,
        filename: str,
        mode: str = "accurate",
        infographic: bool = False,
    ) -> OCRResponse:
        """Process file through Datalab API and return unified response.

        Args:
            file_bytes: Raw file content
            filename: Original filename
            mode: Processing mode (fast, balanced, accurate)
            infographic: Extract table structure with line-by-line breakdown

        Returns:
            OCRResponse with normalized structure
        """
        extras = "infographic" if infographic else None

        result = self._client.convert(
            file_bytes=file_bytes,
            filename=filename,
            mode=mode,
            output_format="json",
            extras=extras,
            mime=None,
        )

        return self._transform_response(result, file_bytes)

    def _crop_and_save_figure(
        self,
        source_bytes: bytes,
        bbox: list[float],
        block_id: str,
    ) -> str | None:
        """Crop figure from source image based on bbox."""
        try:
            image = Image.open(io.BytesIO(source_bytes))
            img_width, img_height = image.size

            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            x1 = max(0, min(x1, img_width))
            y1 = max(0, min(y1, img_height))
            x2 = max(x1 + 1, min(x2, img_width))
            y2 = max(y1 + 1, min(y2, img_height))

            cropped = image.crop((x1, y1, x2, y2))
            output = io.BytesIO()
            cropped.save(output, format="PNG", optimize=True)
            return self._image_store.save(
                output.getvalue(), prefix=f"fig_{hash(block_id) % 10000:04d}"
            )
        except Exception as exc:
            logger.error(f"Failed to crop figure: {exc}")
            return None

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

        pages: list[PageResult] = []
        block_counter = 0

        if not page_nodes:
            # No page wrapper, process children directly
            blocks = self._extract_blocks(
                children, page_idx=0, counter_start=0, source_bytes=source_bytes
            )
            pages.append(PageResult(page_index=0, blocks=blocks))
        else:
            for page_idx, page_node in enumerate(page_nodes):
                bbox = page_node.get("bbox", [])
                page_width = int(bbox[2]) if len(bbox) >= 3 else 0
                page_height = int(bbox[3]) if len(bbox) >= 4 else 0

                page_children = page_node.get("children", [])
                start_counter = block_counter
                blocks = self._extract_blocks(
                    page_children,
                    page_idx=page_idx,
                    counter_start=start_counter,
                    source_bytes=source_bytes,
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
        cost = CostBreakdown.from_datalab(datalab_result.get("cost_breakdown"))

        # Remove base64 images from raw response to reduce size
        raw_response = self._strip_base64(datalab_result)

        return OCRResponse(
            success=datalab_result.get("success", True),
            page_count=datalab_result.get("page_count", len(pages)),
            pages=pages,
            runtime_seconds=datalab_result.get("runtime"),
            cost=cost,
            raw=raw_response,
        )

    def _strip_base64(self, data: dict[str, Any]) -> dict[str, Any]:
        """Clean raw response - remove base64, metadata thừa."""
        import copy

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
    ) -> list[BlockContent]:
        """Extract blocks from Datalab tree structure."""
        blocks: list[BlockContent] = []
        counter = counter_start

        for node in nodes:
            block_type = node.get("block_type", "")
            block_id = node.get("id", f"p{page_idx}_b{counter}")

            # Skip empty pages
            if block_type == "Page":
                continue

            # Map Datalab block types to unified types
            unified_type = self._map_block_type(block_type)

            # Extract text content
            text = ""
            html = node.get("html") or ""

            if block_type == "Text":
                text = node.get("text") or ""
                if not text:
                    text = html_to_text(html)
            else:
                text = html_to_text(html)

            # Extract polygon (fallback to bbox if not available)
            polygon_list = node.get("polygon")
            bbox_list = node.get("bbox", [])

            polygon = None
            if polygon_list and isinstance(polygon_list, list):
                polygon = Polygon.from_list(polygon_list)
            elif bbox_list and len(bbox_list) == 4:
                polygon = Polygon.from_list(
                    [
                        [bbox_list[0], bbox_list[1]],
                        [bbox_list[2], bbox_list[1]],
                        [bbox_list[2], bbox_list[3]],
                        [bbox_list[0], bbox_list[3]],
                    ]
                )

            image_ref: ImageRef | None = None
            if (
                block_type in ("Figure", "Image", "Picture")
                and source_bytes
                and bbox_list
                and len(bbox_list) >= 4
            ):
                file_id = self._crop_and_save_figure(source_bytes, bbox_list, block_id)
                if file_id:
                    image_ref = ImageRef(
                        file_id=file_id,
                        url=f"/api/v1/files/{file_id}",
                        description=text or "",
                        caption=None,
                    )

            # Create block
            counter += 1
            block = BlockContent(
                id=block_id,
                block_type=unified_type,
                content=text.strip() if text else "",
                html=html if html else None,
                polygon=polygon,
                confidence=node.get("confidence", 1.0),
                reading_order=counter,
                language=node.get("language"),
                image=image_ref,
            )
            blocks.append(block)

            # Recursively process children
            for child in node.get("children", []):
                child_blocks = self._extract_blocks(
                    [child],
                    page_idx=page_idx,
                    counter_start=counter,
                    source_bytes=source_bytes,
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
