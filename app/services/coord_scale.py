"""Scale OCR coordinates from API space to input image space."""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional, Tuple


def _find_page_bbox(tree: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    nodes = tree.get("children") or []
    page = tree
    for node in nodes:
        if node.get("block_type") == "Page":
            page = node
            break
    bbox = page.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    width = float(bbox[2]) - float(bbox[0])
    height = float(bbox[3]) - float(bbox[1])
    if width <= 0 or height <= 0:
        return None
    return width, height


def _scale_node(node: Dict[str, Any], sx: float, sy: float) -> Dict[str, Any]:
    scaled = copy.deepcopy(node)
    bbox = scaled.get("bbox")
    if isinstance(bbox, list) and len(bbox) == 4:
        scaled["bbox"] = [
            int(round(float(bbox[0]) * sx)),
            int(round(float(bbox[1]) * sy)),
            int(round(float(bbox[2]) * sx)),
            int(round(float(bbox[3]) * sy)),
        ]
    polygon = scaled.get("polygon")
    if isinstance(polygon, list):
        new_poly = []
        for point in polygon:
            if isinstance(point, list) and len(point) == 2:
                new_poly.append(
                    [
                        int(round(float(point[0]) * sx)),
                        int(round(float(point[1]) * sy)),
                    ]
                )
        if new_poly:
            scaled["polygon"] = new_poly
    children = scaled.get("children")
    if isinstance(children, list):
        scaled["children"] = [_scale_node(child, sx, sy) for child in children]
    return scaled


def scale_tree_to_image(
    tree: Dict[str, Any], image_size: Tuple[int, int]
) -> Dict[str, Any]:
    """Return tree with bbox/polygon scaled to input image size."""
    api_size = _find_page_bbox(tree)
    if not api_size:
        return tree
    img_w, img_h = image_size
    api_w, api_h = api_size
    sx = float(img_w) / api_w
    sy = float(img_h) / api_h
    if abs(sx - 1.0) < 1e-6 and abs(sy - 1.0) < 1e-6:
        return tree
    return _scale_node(tree, sx, sy)
