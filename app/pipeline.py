"""Simple OCR pipeline: file -> Datalab -> structured blocks.

Supports images (JPG, PNG, WEBP) and PDFs (all pages).
Bbox coordinates are returned in original document frame.
"""

from __future__ import annotations

import logging
import uuid
from io import BytesIO
from typing import Any

from PIL import Image

from app.core.config import Settings, get_settings
from app.services.datalab_client import DatalabClient

logger = logging.getLogger(__name__)


def _load_image(raw: bytes) -> Image.Image:
    """Decode image bytes to RGB PIL Image."""
    img = Image.open(BytesIO(raw))
    img.load()
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _get_pdf_page_sizes(raw: bytes) -> list[dict[str, int]]:
    """Return page sizes for PDF at 1x resolution."""
    try:
        import fitz
        doc = fitz.open(stream=raw, filetype="pdf")
        sizes = [{"width": int(doc[i].rect.width), "height": int(doc[i].rect.height)}
                 for i in range(len(doc))]
        doc.close()
        return sizes
    except Exception as exc:
        logger.warning("Cannot read PDF sizes: %s", exc)
        return []


def _extract_blocks(children: list[dict], page_idx: int = 0) -> list[dict]:
    """Flatten tree to list of blocks."""
    from app.services.html_clean import html_to_text

    blocks = []
    for child in children:
        blocks.extend(_extract_blocks(child.get("children") or [], page_idx))

        btype = child.get("block_type", "")
        if btype not in ("Text", "Table", "Figure"):
            continue

        raw_text = child.get("text") or ""
        if not raw_text:
            raw_text = html_to_text(child.get("html") or "")

        blocks.append({
            "index": len(blocks),
            "id": child.get("id", f"blk_{uuid.uuid4().hex[:6]}"),
            "type": btype.lower(),
            "text": raw_text,
            "html": child.get("html") or "",
            "bbox": child.get("bbox") or [],
            "page": child.get("page_index", page_idx),
        })
    return blocks


def _assign_page_info(tree: dict, page_sizes: list[dict]) -> None:
    """Assign page_index and dimensions to Page nodes in tree."""
    children = tree.get("children") or []
    page_nodes = [c for c in children if c.get("block_type") == "Page"]
    for i, node in enumerate(page_nodes):
        node["page_index"] = i
        if i < len(page_sizes):
            node["width"] = page_sizes[i]["width"]
            node["height"] = page_sizes[i]["height"]


def _process_image(
    raw: bytes,
    filename: str,
    client: DatalabClient,
    settings: Settings,
) -> dict:
    """OCR a single image."""
    img = _load_image(raw)
    w, h = img.size
    logger.info("[pipeline] PIL image size: %dx%d, raw bytes len: %d", w, h, len(raw))

    # Convert to JPEG for upload (PIL strips EXIF, this defines the coordinate frame)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    payload = buf.getvalue()

    # Re-check size after re-encoding
    rechecked = Image.open(BytesIO(payload))
    rw, rh = rechecked.size
    logger.info("[pipeline] after JPEG re-encode: %dx%d", rw, rh)

    try:
        result = client.convert(payload, filename, "accurate", "json", mime="image/jpeg")
    except RuntimeError as exc:
        logger.error("Datalab OCR failed for %s: %s", filename, exc)
        raise

    tree = result.get("json", {})
    if not isinstance(tree, dict):
        raise ValueError("Datalab returned invalid JSON")

    children = tree.get("children") or []

    # Log raw bboxes from Datalab response
    for i, child in enumerate(children[:5]):
        logger.info("[pipeline] child[%d] type=%s bbox=%s", i, child.get("block_type"), child.get("bbox"))

    # Get Datalab's internal page size (may differ from input due to resizing)
    dl_w, dl_h = rw, rh
    for node in children:
        if node.get("block_type") == "Page":
            bbox = node.get("bbox") or []
            if len(bbox) == 4:
                dl_w = int(bbox[2])
                dl_h = int(bbox[3])
            node["page_index"] = 0
            node["width"] = rw
            node["height"] = rh
            break

    blocks = _extract_blocks(children)
    logger.info("Image %s: input=%dx%d, datalab=%dx%d, blocks=%d", filename, rw, rh, dl_w, dl_h, len(blocks))

    return {
        "document_type": "image",
        "page_count": 1,
        "page_sizes": [{"width": rw, "height": rh}],
        "children": children,
        "blocks": blocks,
        "image_size": {"width": dl_w, "height": dl_h},
    }


def _process_pdf(
    raw: bytes,
    filename: str,
    client: DatalabClient,
    settings: Settings,
) -> dict:
    """OCR a PDF - send directly to Datalab for best multi-page handling."""
    page_sizes = _get_pdf_page_sizes(raw)

    try:
        result = client.convert(raw, filename, "accurate", "json", mime="application/pdf")
    except RuntimeError as exc:
        logger.error("Datalab PDF OCR failed for %s: %s", filename, exc)
        raise

    tree = result.get("json", {})
    if not isinstance(tree, dict):
        raise ValueError("Datalab returned invalid JSON")

    _assign_page_info(tree, page_sizes)

    children = tree.get("children") or []
    blocks = _extract_blocks(children)
    page_count = len(page_sizes)

    logger.info("PDF %s: %d pages, %d blocks", filename, page_count, len(blocks))

    return {
        "document_type": "pdf",
        "page_count": page_count,
        "page_sizes": page_sizes,
        "children": children,
        "blocks": blocks,
        "image_size": page_sizes[0] if page_sizes else {"width": 0, "height": 0},
    }


def process_image_bytes(
    raw: bytes,
    filename: str,
    client: DatalabClient | None = None,
    settings: Settings | None = None,
) -> dict:
    """OCR an image or PDF. Returns structured blocks with bbox in original frame."""
    settings = settings or get_settings()
    client = client or DatalabClient(settings=settings)

    # Detect PDF by magic bytes
    is_pdf = raw[:4] == b"%PDF"

    if is_pdf:
        return _process_pdf(raw, filename, client, settings)
    else:
        return _process_image(raw, filename, client, settings)
