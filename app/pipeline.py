"""Run accurate convert then optional infographic line refinement."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from app.core.config import Settings, get_settings
from app.services.coord_scale import scale_tree_to_image
from app.services.datalab_client import DatalabConvertClient
from app.services.html_clean import clean_html_fragment
from app.services.tree_refiner import refine_document_tree

logger = logging.getLogger(__name__)


def _load_image(path: Path) -> Image.Image:
    img = Image.open(path)
    return img.convert("RGB")


def _load_image_bytes(raw: bytes) -> Image.Image:
    img = Image.open(BytesIO(raw))
    return img.convert("RGB")


def _flatten_page_html(page: Dict[str, Any]) -> None:
    """Replace Page html with concatenated cleaned child fragments."""
    parts: List[str] = []
    for ch in page.get("children") or []:
        h = ch.get("html")
        if h:
            c = clean_html_fragment(h)
            if c:
                parts.append(c)
    if parts:
        page["html"] = "\n".join(parts)


def _walk_pages(tree: Dict[str, Any]) -> None:
    for node in tree.get("children") or []:
        if node.get("block_type") == "Page":
            _flatten_page_html(node)
            _walk_pages(node)


def process_image_file(
    path: str | Path,
    client: Optional[DatalabConvertClient] = None,
    settings: Optional[Settings] = None,
    refine: bool = True,
) -> Dict[str, Any]:
    """Accurate JSON OCR, then infographic refinement and html cleanup."""
    settings = settings or get_settings()
    client = client or DatalabConvertClient(settings=settings)
    p = Path(path)
    raw = p.read_bytes()
    image = _load_image(p)

    logger.info("datalab accurate convert: %s", p.name)
    base = client.convert(
        raw,
        p.name,
        "accurate",
        "json",
        extras=None,
    )
    tree = base.get("json")
    if not isinstance(tree, dict):
        raise ValueError("convert json missing")
    tree = scale_tree_to_image(tree, image.size)
    out_tree = (
        refine_document_tree(
            tree,
            image,
            client=client,
            settings=settings,
        )
        if refine
        else tree
    )
    _walk_pages(out_tree)

    meta = base.get("metadata")
    return {
        "children": out_tree.get("children", []),
        "metadata": meta,
    }


def process_image_files(
    paths: List[str | Path],
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """Process many images; each completes before the next starts."""
    return [process_image_file(p, **kwargs) for p in paths]


def process_image_bytes(
    raw: bytes,
    filename: str,
    client: Optional[DatalabConvertClient] = None,
    settings: Optional[Settings] = None,
    refine: bool = True,
) -> Dict[str, Any]:
    """Accurate JSON OCR for an in-memory image."""
    settings = settings or get_settings()
    client = client or DatalabConvertClient(settings=settings)
    image = _load_image_bytes(raw)

    logger.info("datalab accurate convert: %s", filename)
    base = client.convert(
        raw,
        filename,
        "accurate",
        "json",
        extras=None,
    )
    tree = base.get("json")
    if not isinstance(tree, dict):
        raise ValueError("convert json missing")
    tree = scale_tree_to_image(tree, image.size)
    out_tree = (
        refine_document_tree(
            tree,
            image,
            client=client,
            settings=settings,
        )
        if refine
        else tree
    )
    _walk_pages(out_tree)
    return {
        "children": out_tree.get("children", []),
        "metadata": base.get("metadata"),
    }
