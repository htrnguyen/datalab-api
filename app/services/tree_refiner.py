"""Detect multi-line blocks and recurse infographic splits."""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from app.core.config import Settings, get_settings
from app.services.bbox_utils import crop_png_bytes
from app.services.datalab_client import DatalabConvertClient
from app.services.html_clean import clean_html_fragment
from app.services.infographic_remap import infographic_mapped_children

logger = logging.getLogger(__name__)


def is_multi_line_html(html: str) -> bool:
    """True if fragment likely contains multiple visual lines."""
    if not html or not html.strip():
        return False
    low = html.lower()
    if "<br" in low:
        return True
    soup = BeautifulSoup(html, "html.parser")
    paragraphs = soup.find_all("p")
    if len(paragraphs) > 1:
        return True
    for p in paragraphs:
        if p.find("br"):
            return True
    blocks = soup.find_all("math", attrs={"display": "block"})
    return len(blocks) > 1


def _norm_sig(nodes: List[Dict[str, Any]]) -> Tuple[str, ...]:
    parts = [clean_html_fragment(n.get("html") or "") for n in nodes]
    return tuple(sorted(parts))


def refine_block(
    node: Dict[str, Any],
    image,
    client: DatalabConvertClient,
    settings: Settings,
    depth: int,
) -> List[Dict[str, Any]]:
    """Return one or more nodes with line-level splits where possible."""
    bt = node.get("block_type")
    if bt == "Figure":
        return [copy.deepcopy(node)]
    if bt == "Page":
        node = copy.deepcopy(node)
        ch = node.get("children") or []
        node["children"] = refine_children(ch, image, client, settings, depth)
        return [node]

    html_raw = node.get("html") or ""
    cleaned = clean_html_fragment(html_raw)
    node = copy.deepcopy(node)
    if cleaned:
        node["html"] = cleaned
        html_raw = cleaned

    if not node.get("bbox") or not is_multi_line_html(html_raw):
        return [node]

    if depth >= settings.refine_max_depth:
        return [node]

    crop_bytes, crop_rect = crop_png_bytes(
        image,
        node["bbox"],
        settings.bbox_padding_ratio,
    )
    prefix = node.get("id") or "blk"
    try:
        mapped1 = infographic_mapped_children(
            client, crop_bytes, crop_rect, prefix
        )
    except Exception as exc:
        logger.warning(
            "infographic refine failed for block=%s, keep original bbox: %s",
            prefix,
            exc,
        )
        return [node]

    if (
        len(mapped1) == 1
        and is_multi_line_html(mapped1[0].get("html") or "")
    ):
        try:
            mapped2 = infographic_mapped_children(
                client, crop_bytes, crop_rect, prefix
            )
        except Exception as exc:
            logger.warning(
                "infographic second pass failed for block=%s: %s",
                prefix,
                exc,
            )
            return [node]
        if _norm_sig(mapped1) == _norm_sig(mapped2):
            logger.info("infographic stable; keeping block %s", prefix)
            return [node]
        mapped1 = mapped2

    expanded: List[Dict[str, Any]] = []
    for child in mapped1:
        expanded.extend(
            refine_block(child, image, client, settings, depth + 1)
        )
    return expanded


def refine_children(
    children: List[Dict[str, Any]],
    image,
    client: DatalabConvertClient,
    settings: Settings,
    depth: int,
) -> List[Dict[str, Any]]:
    """Refine each child, flattening replacements."""
    out: List[Dict[str, Any]] = []
    for ch in children:
        out.extend(refine_block(ch, image, client, settings, depth))
    out.sort(key=lambda n: (n.get("bbox") or [0, 0, 0, 0])[1])
    return out


def refine_document_tree(
    tree: Dict[str, Any],
    image,
    client: Optional[DatalabConvertClient] = None,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """Return new tree with refined text blocks."""
    settings = settings or get_settings()
    client = client or DatalabConvertClient(settings=settings)
    doc = copy.deepcopy(tree)
    kids = doc.get("children") or []
    new_kids: List[Dict[str, Any]] = []
    for k in kids:
        if k.get("block_type") == "Page":
            pg = copy.deepcopy(k)
            pg["children"] = refine_children(
                pg.get("children") or [],
                image,
                client,
                settings,
                0,
            )
            new_kids.append(pg)
        else:
            new_kids.extend(refine_block(k, image, client, settings, 0))
    doc["children"] = new_kids
    return doc
