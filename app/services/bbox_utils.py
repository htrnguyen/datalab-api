"""Crop regions and map bboxes from API space to original image pixels."""

from __future__ import annotations

import io
from typing import List, Tuple

from PIL import Image


def as_bbox_int(bbox: List[int]) -> Tuple[int, int, int, int]:
    """Return x0,y0,x1,y1 as integers."""
    x0, y0, x1, y1 = (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
    return x0, y0, x1, y1


def pad_bbox(
    bbox: List[int],
    img_w: int,
    img_h: int,
    ratio: float,
) -> Tuple[int, int, int, int]:
    """Expand bbox by ratio of its size, clamped to image bounds."""
    x0, y0, x1, y1 = as_bbox_int(bbox)
    w = max(1, x1 - x0)
    h = max(1, y1 - y0)
    dx = int(w * ratio)
    dy = int(h * ratio)
    nx0 = max(0, x0 - dx)
    ny0 = max(0, y0 - dy)
    nx1 = min(img_w, x1 + dx)
    ny1 = min(img_h, y1 + dy)
    return nx0, ny0, nx1, ny1


def crop_png_bytes(
    image: Image.Image,
    bbox: List[int],
    pad: float,
) -> Tuple[bytes, Tuple[int, int, int, int]]:
    """Return PNG bytes and the crop rectangle in full-image coordinates."""
    rgb = image.convert("RGB")
    w, h = rgb.size
    x0, y0, x1, y1 = pad_bbox(bbox, w, h, pad)
    crop = rgb.crop((x0, y0, x1, y1))
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    return buf.getvalue(), (x0, y0, x1, y1)


def map_bbox_to_full_image(
    child_bbox: List[int],
    api_page_bbox: List[int],
    crop_rect: Tuple[int, int, int, int],
) -> List[int]:
    """Map child bbox from sub-convert page space to full-image coords."""
    cx0, cy0, cx1, cy1 = (float(crop_rect[0]), float(crop_rect[1]),
                          float(crop_rect[2]), float(crop_rect[3]))
    px0, py0, px1, py1 = [float(x) for x in api_page_bbox]
    bx0, by0, bx1, by1 = [float(x) for x in child_bbox]

    cw = max(1.0, cx1 - cx0)
    ch = max(1.0, cy1 - cy0)
    pw = max(1.0, px1 - px0)
    ph = max(1.0, py1 - py0)
    sx = cw / pw
    sy = ch / ph

    def m(bx_a: float, by_a: float, bx_b: float, by_b: float) -> List[int]:
        return [
            int(round(cx0 + (bx_a - px0) * sx)),
            int(round(cy0 + (by_a - py0) * sy)),
            int(round(cx0 + (bx_b - px0) * sx)),
            int(round(cy0 + (by_b - py0) * sy)),
        ]

    return m(bx0, by0, bx1, by1)
