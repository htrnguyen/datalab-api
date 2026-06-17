"""Image extraction service - crops and saves figures from documents."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)


class ImageExtractor:
    """Extract and save cropped images from documents."""

    def __init__(self, storage_dir: Path | None = None):
        self._storage_dir = storage_dir or Path("uploads")
        self._storage_dir.mkdir(exist_ok=True, parents=True)

    def extract_figure(
        self,
        source_bytes: bytes,
        bbox: list[float],
        page_width: int,
        page_height: int,
        original_width: int | None = None,
        original_height: int | None = None,
        description: str = "",
    ) -> dict[str, Any] | None:
        """Extract a figure from source image based on bounding box.

        Args:
            source_bytes: Original image/PDF bytes
            bbox: Bounding box [x1, y1, x2, y2] in PDF/image coordinates
            page_width: Page width in Datalab coordinates
            page_height: Page height in Datalab coordinates
            original_width: Original image width (for scaling)
            original_height: Original image height (for scaling)
            description: Image description from OCR

        Returns:
            Dict with file_id and metadata, or None if extraction fails
        """
        try:
            x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]

            # Load image
            image = Image.open(io.BytesIO(source_bytes))
            img_width, img_height = image.size

            # Calculate scale factor if dimensions differ
            scale_x = img_width / page_width if page_width > 0 else 1
            scale_y = img_height / page_height if page_height > 0 else 1

            # Scale bbox to actual image coordinates
            crop_x1 = int(x1 * scale_x)
            crop_y1 = int(y1 * scale_y)
            crop_x2 = int(x2 * scale_x)
            crop_y2 = int(y2 * scale_y)

            # Ensure valid crop area
            crop_x1 = max(0, min(crop_x1, img_width))
            crop_y1 = max(0, min(crop_y1, img_height))
            crop_x2 = max(crop_x1 + 1, min(crop_x2, img_width))
            crop_y2 = max(crop_y1 + 1, min(crop_y2, img_height))

            # Crop image
            cropped = image.crop((crop_x1, crop_y1, crop_x2, crop_y2))

            # Save as PNG for quality
            output = io.BytesIO()
            cropped.save(output, format="PNG", optimize=True)
            output_bytes = output.getvalue()

            # Save to storage
            file_id = self._save_image(output_bytes, f"figure_{x1}_{y1}.png")

            return {
                "file_id": file_id,
                "description": description,
                "caption": None,
                "width": crop_x2 - crop_x1,
                "height": crop_y2 - crop_y1,
            }

        except Exception as exc:
            logger.error(f"Failed to extract figure: {exc}")
            return None

    def _save_image(self, image_bytes: bytes, filename: str) -> str:
        """Save image bytes and return file_id."""
        import hashlib
        import uuid

        file_id = f"img_{hashlib.md5(image_bytes[:1024]).hexdigest()[:8]}_{uuid.uuid4().hex[:6]}"
        file_path = self._storage_dir / f"{file_id}.png"

        with open(file_path, "wb") as f:
            f.write(image_bytes)

        return file_id

    def extract_figures_from_blocks(
        self,
        source_bytes: bytes,
        blocks: list[dict[str, Any]],
        page_width: int,
        page_height: int,
    ) -> dict[str, dict[str, Any]]:
        """Extract all figure blocks from a page.

        Returns:
            Dict mapping block_id to image metadata
        """
        results = {}
        for block in blocks:
            if block.get("block_type") == "Figure":
                block_id = block.get("id", "")
                bbox = block.get("bbox", [])
                description = block.get("text", "") or block.get("html", "")

                if bbox and len(bbox) >= 4:
                    result = self.extract_figure(
                        source_bytes=source_bytes,
                        bbox=bbox,
                        page_width=page_width,
                        page_height=page_height,
                        description=description,
                    )
                    if result:
                        results[block_id] = result

        return results
