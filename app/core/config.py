"""Load Datalab API keys and tunables from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List


def _split_keys(raw: str) -> List[str]:
    parts = []
    for line in raw.replace(",", "\n").splitlines():
        k = line.strip()
        if k:
            parts.append(k)
    return parts


def load_api_keys() -> List[str]:
    """Keys from DATALAB_API_KEYS as comma-separated list."""
    bulk = os.getenv("DATALAB_API_KEYS", "")
    keys = _split_keys(bulk)
    if not keys:
        msg = "Set DATALAB_API_KEYS in environment (comma-separated)."
        raise RuntimeError(msg)
    return keys


@dataclass(frozen=True)
class Settings:
    base_url: str
    poll_interval_sec: float
    poll_timeout_sec: float
    refine_max_depth: int
    bbox_padding_ratio: float
    http_timeout_sec: float
    max_retries: int
    max_upload_size_mb: float


def get_settings() -> Settings:
    base = os.getenv("DATALAB_BASE_URL", "https://www.datalab.to/api/v1")
    return Settings(
        base_url=base.rstrip("/"),
        poll_interval_sec=float(os.getenv("DATALAB_POLL_INTERVAL", "2")),
        poll_timeout_sec=float(os.getenv("DATALAB_POLL_TIMEOUT", "120")),
        refine_max_depth=int(os.getenv("DATALAB_REFINE_MAX_DEPTH", "6")),
        bbox_padding_ratio=float(os.getenv("DATALAB_BBOX_PADDING", "0.02")),
        # 90s is enough for any single image upload at our 1800px cap.
        # Datalab itself usually accepts the upload in <10s on a good
        # link; this leaves headroom for the long-tail of slow networks.
        http_timeout_sec=float(os.getenv("DATALAB_HTTP_TIMEOUT", "90")),
        max_retries=int(os.getenv("DATALAB_MAX_RETRIES", "2")),
        max_upload_size_mb=float(os.getenv("MAX_UPLOAD_SIZE_MB", "50")),
    )
