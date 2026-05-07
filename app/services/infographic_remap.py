"""Infographic convert helper with bbox remap to full image."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

from app.services.bbox_utils import map_bbox_to_full_image
from app.services.datalab_client import DatalabConvertClient
from app.services.html_clean import clean_html_fragment


def remap_page_children(
    page_api: Dict[str, Any],
    crop_rect: Tuple[int, int, int, int],
    id_prefix: str,
) -> List[Dict[str, Any]]:
    """Map API nodes from cropped subdocument to full-image coordinates."""
    api_bbox = page_api.get("bbox") or [0, 0, 1, 1]
    out: List[Dict[str, Any]] = []
    for i, ch in enumerate(page_api.get("children") or []):
        node = copy.deepcopy(ch)
        bb = node.get("bbox")
        if bb:
            node["bbox"] = map_bbox_to_full_image(bb, api_bbox, crop_rect)
        poly = node.get("polygon")
        if poly:
            new_poly = []
            for pt in poly:
                mapped = map_bbox_to_full_image(
                    [pt[0], pt[1], pt[0], pt[1]],
                    api_bbox,
                    crop_rect,
                )
                new_poly.append([mapped[0], mapped[1]])
            node["polygon"] = new_poly
        node["id"] = f"{id_prefix}/ig/{i}"
        html = node.get("html")
        if html:
            node["html"] = clean_html_fragment(html)
        out.append(node)
    return out


def infographic_mapped_children(
    client: DatalabConvertClient,
    crop_bytes: bytes,
    crop_rect: Tuple[int, int, int, int],
    id_prefix: str,
) -> List[Dict[str, Any]]:
    """Run infographic accurate convert on a crop; return remapped children."""
    result = client.convert(
        crop_bytes,
        "crop.png",
        "accurate",
        "json",
        extras="infographic",
    )
    tree = result.get("json") or {}
    kids = tree.get("children") or []
    page = tree
    for ch in kids:
        if ch.get("block_type") == "Page":
            page = ch
            break
    return remap_page_children(page, crop_rect, id_prefix)
