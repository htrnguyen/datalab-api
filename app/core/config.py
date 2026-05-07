"""Load Datalab API keys and tunables from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

TRUTHY = {"1", "true", "yes", "on"}


def _split_keys(raw: str) -> List[str]:
    parts = []
    for line in raw.replace(",", "\n").splitlines():
        k = line.strip()
        if k:
            parts.append(k)
    return parts


def _as_bool(raw: str, default: bool) -> bool:
    val = raw.strip().lower()
    if not val:
        return default
    return val in TRUTHY


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


def get_settings() -> Settings:
    base = os.getenv("DATALAB_BASE_URL", "https://www.datalab.to/api/v1")
    return Settings(
        base_url=base.rstrip("/"),
        poll_interval_sec=float(os.getenv("DATALAB_POLL_INTERVAL", "2")),
        poll_timeout_sec=float(os.getenv("DATALAB_POLL_TIMEOUT", "30")),
        refine_max_depth=int(os.getenv("DATALAB_REFINE_MAX_DEPTH", "6")),
        bbox_padding_ratio=float(os.getenv("DATALAB_BBOX_PADDING", "0.02")),
        http_timeout_sec=float(os.getenv("DATALAB_HTTP_TIMEOUT", "30")),
        max_retries=int(os.getenv("DATALAB_MAX_RETRIES", "2")),
    )


@dataclass(frozen=True)
class PaddleTextDetSettings:
    model_name: str
    model_dir: Optional[str]
    device: str
    eager_load: bool


def get_paddle_text_det_settings() -> PaddleTextDetSettings:
    raw_dir = os.getenv("PADDLE_TEXT_DET_MODEL_DIR", "").strip()
    return PaddleTextDetSettings(
        model_name=os.getenv(
            "PADDLE_TEXT_DET_MODEL_NAME",
            "PP-OCRv5_server_det",
        ),
        model_dir=raw_dir or None,
        device=os.getenv("PADDLE_TEXT_DET_DEVICE", "gpu:0"),
        eager_load=_as_bool(
            os.getenv("PADDLE_TEXT_DET_EAGER_LOAD", "1"),
            default=True,
        ),
    )
