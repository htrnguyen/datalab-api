"""Application configuration and settings."""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

HEALTH_URL = "https://www.datalab.to/api/v1/health"
HEALTH_TIMEOUT = 10.0


def _split_keys(raw: str) -> list[str]:
    parts = []
    for line in raw.replace(",", "\n").splitlines():
        k = line.strip()
        if k:
            parts.append(k)
    return parts


async def _check_key_health(api_key: str) -> tuple[str, bool]:
    """Check if an API key is valid by calling /health endpoint.

    Returns:
        Tuple of (api_key, is_valid)
    """
    try:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
            resp = await client.get(
                HEALTH_URL,
                headers={"X-Api-Key": api_key},
            )
            is_valid = resp.status_code == 200
            return api_key, is_valid
    except Exception as e:
        logger.warning("Key health check failed: %s", e)
        return api_key, False


async def validate_api_keys(api_keys: list[str]) -> list[str]:
    """Validate all API keys concurrently, return only valid ones.

    Args:
        api_keys: List of API keys to validate

    Returns:
        List of valid API keys only
    """
    if not api_keys:
        return []

    results = await asyncio.gather(*[_check_key_health(k) for k in api_keys])

    valid_keys = []
    invalid_count = 0

    for key, is_valid in results:
        if is_valid:
            valid_keys.append(key)
        else:
            invalid_count += 1
            masked = f"{key[:6]}...{key[-4:]}" if len(key) > 12 else "***"
            logger.warning("Invalid API key detected and removed: %s", masked)

    total = len(api_keys)
    logger.info(
        "API key validation: %d/%d valid",
        len(valid_keys),
        total,
    )

    if invalid_count:
        logger.warning(
            "Removed %d invalid key(s). %d key(s) remaining.",
            invalid_count,
            len(valid_keys),
        )

    if not valid_keys:
        raise RuntimeError(
            f"All {total} API keys failed validation. "
            "Check your DATALAB_API_KEYS environment variable."
        )

    return valid_keys


def load_api_keys() -> list[str]:
    bulk = os.getenv("DATALAB_API_KEYS", "")
    keys = _split_keys(bulk)
    if not keys:
        msg = "Set DATALAB_API_KEYS in environment (comma-separated)."
        raise RuntimeError(msg)
    return keys


async def load_and_validate_api_keys() -> list[str]:
    """Load and validate API keys on startup.

    Returns:
        List of valid API keys
    """
    keys = load_api_keys()
    return await validate_api_keys(keys)


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
