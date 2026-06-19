from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _split_keys(raw: str) -> list[str]:
    parts = []
    for line in raw.replace(",", "\n").splitlines():
        k = line.strip()
        if k:
            parts.append(k)
    return parts


def load_api_keys() -> list[str]:
    bulk = os.getenv("DATALAB_API_KEYS", "")
    keys = _split_keys(bulk)
    if not keys:
        msg = "Set DATALAB_API_KEYS in environment (comma-separated)."
        raise RuntimeError(msg)
    return keys


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "pdf", "tiff", "tif"}


@dataclass(frozen=True)
class Settings:
    base_url: str
    poll_interval_sec: float
    poll_timeout_sec: float
    http_timeout_sec: float
    max_retries: int
    max_upload_size_mb: float
    debug_dir: Path
    debug_log_enabled: bool
    debug_save_response: bool
    max_concurrent_requests: int = 5
    allowed_extensions: frozenset[str] = field(default_factory=lambda: frozenset(ALLOWED_EXTENSIONS))


def get_settings() -> Settings:
    base = os.getenv("DATALAB_BASE_URL", "https://www.datalab.to/api/v1")
    debug = Path(os.getenv("DEBUG_DIR", "debug_logs"))
    debug_log_enabled = os.getenv("DEBUG_LOG_ENABLED", "true").lower() not in {"0", "false", "no"}
    debug_save_response = os.getenv("DEBUG_SAVE_RESPONSE", "false").lower() in {"1", "true", "yes"}
    max_concurrent = int(os.getenv("MAX_CONCURRENT_REQUESTS", "5"))

    allowed_raw = os.getenv("ALLOWED_EXTENSIONS", "")
    if allowed_raw:
        allowed = frozenset(ext.strip().lower() for ext in allowed_raw.split(",") if ext.strip())
    else:
        allowed = frozenset(ALLOWED_EXTENSIONS)

    return Settings(
        base_url=base.rstrip("/"),
        poll_interval_sec=float(os.getenv("DATALAB_POLL_INTERVAL", "2")),
        poll_timeout_sec=float(os.getenv("DATALAB_POLL_TIMEOUT", "120")),
        http_timeout_sec=float(os.getenv("DATALAB_HTTP_TIMEOUT", "90")),
        max_retries=int(os.getenv("DATALAB_MAX_RETRIES", "2")),
        max_upload_size_mb=float(os.getenv("MAX_UPLOAD_SIZE_MB", "50")),
        debug_dir=debug,
        debug_log_enabled=debug_log_enabled,
        debug_save_response=debug_save_response,
        max_concurrent_requests=max_concurrent,
        allowed_extensions=allowed,
    )
