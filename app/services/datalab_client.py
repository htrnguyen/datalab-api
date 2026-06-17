"""Datalab /convert API client with retry and key rotation."""

from __future__ import annotations

import logging
import mimetypes
import re
import time
from typing import Any

import httpx

from app.core.config import Settings, get_settings, load_api_keys

logger = logging.getLogger(__name__)

RETRY_STATUS = {401, 403, 429}
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class DatalabError(RuntimeError):
    """Conversion failed or all keys exhausted."""


class DatalabClient:
    """Submit files to Datalab /convert and poll until complete."""

    def __init__(
        self,
        keys: list[str] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._keys = list(keys) if keys else load_api_keys()
        self._idx = 0
        self._settings = settings or get_settings()

    @property
    def _current_key(self) -> str:
        if self._idx >= len(self._keys):
            raise DatalabError("No API key available")
        return self._keys[self._idx]

    def _rotate(self) -> None:
        """Move to next key."""
        self._idx = (self._idx + 1) % len(self._keys)

    def convert(
        self,
        file_bytes: bytes,
        filename: str,
        mode: str = "accurate",
        output_format: str = "json",
        extras: str | None = None,
        mime: str | None = None,
    ) -> dict[str, Any]:
        """Upload file, poll until done, return result JSON."""
        self._idx = 0
        max_retries = max(1, self._settings.max_retries)
        last_err: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                return self._convert_once(file_bytes, filename, mode, output_format, extras, mime)
            except httpx.HTTPStatusError as exc:
                last_err = exc
                if exc.response.status_code in RETRY_STATUS and attempt < max_retries:
                    self._rotate()
                    time.sleep(min(8.0, 2 ** attempt))
                    continue
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_err = exc
                if attempt < max_retries:
                    time.sleep(min(8.0, 2 ** attempt))
                    continue
            except Exception as exc:
                logger.exception("convert failed")
                raise DatalabError(str(exc)) from exc

        raise DatalabError(str(last_err) if last_err else "convert failed")

    def _convert_once(
        self,
        file_bytes: bytes,
        filename: str,
        mode: str,
        output_format: str,
        extras: str | None,
        mime: str | None,
    ) -> dict[str, Any]:
        """Single convert attempt: upload + poll."""
        url = f"{self._settings.base_url}/convert"
        safe_name = self._safe_filename(filename)

        # Determine MIME type
        if mime:
            final_mime = mime
        else:
            final_mime, _ = mimetypes.guess_type(safe_name)
            if not final_mime:
                final_mime = "application/octet-stream"

        # Build request
        timeout = httpx.Timeout(
            connect=10.0,
            write=self._settings.http_timeout_sec,
            read=self._settings.http_timeout_sec,
            pool=10.0,
        )

        data: dict[str, Any] = {"mode": mode, "output_format": output_format}
        if extras:
            data["extras"] = extras

        # Reuse client for connection pooling
        if not hasattr(self, "_http"):
            self._http = httpx.Client(timeout=timeout)
        http = self._http

        resp = http.post(
            url,
            headers={"X-API-Key": self._current_key},
            data=data,
            files={"file": (safe_name, file_bytes, final_mime)},
        )

        if resp.status_code >= 400:
            logger.error("Datalab error %d: %s", resp.status_code, resp.text[:300])
            resp.raise_for_status()

        body = resp.json()
        if not body.get("success"):
            raise DatalabError(f"Datalab submit failed: {body}")

        return self._poll(body["request_check_url"])

    def _poll(self, check_url: str) -> dict[str, Any]:
        """Poll check_url until conversion is complete."""
        deadline = time.monotonic() + self._settings.poll_timeout_sec
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)

        # Reuse client for connection pooling
        if not hasattr(self, "_http"):
            self._http = httpx.Client(timeout=timeout)
        http = self._http

        while time.monotonic() < deadline:
            resp = http.get(check_url, headers={"X-API-Key": self._current_key})
            resp.raise_for_status()
            result = resp.json()

            status = result.get("status")
            if status == "complete":
                if not result.get("success", True):
                    raise DatalabError(f"Conversion failed: {result.get('error', 'unknown')}")
                return result
            if status == "failed":
                raise DatalabError(f"Conversion failed: {result.get('error', 'unknown')}")

            time.sleep(self._settings.poll_interval_sec)

        raise DatalabError("Conversion timed out")

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """Sanitize filename for multipart upload."""
        base = (filename or "upload").strip()
        ext = "png"
        if "." in base:
            base, ext = base.rsplit(".", 1)
            ext = ext.lower()
        base = SAFE_FILENAME_RE.sub("_", base).strip("._-") or "upload"
        return f"{base}.{ext}"
