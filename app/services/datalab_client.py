"""Datalab /convert submit + poll with API key rotation."""

from __future__ import annotations

import logging
import mimetypes
import re
import time
from typing import Any, Callable, Dict, Optional

import httpx

from app.core.config import Settings, get_settings, load_api_keys

logger = logging.getLogger(__name__)

RETRY_STATUS = {401, 403, 429}
SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class DatalabError(RuntimeError):
    """All keys failed or conversion failed."""


class KeyRing:
    """Rotate keys on rate limit or auth errors."""

    def __init__(self, keys: list[str]) -> None:
        if not keys:
            raise ValueError("keys required")
        self._keys = list(keys)
        self._idx = 0

    def __len__(self) -> int:
        return len(self._keys)

    def current(self) -> str:
        if self._idx >= len(self._keys):
            raise DatalabError("No API key available.")
        return self._keys[self._idx]

    def rotate(self) -> None:
        self._idx += 1

    def exhausted(self) -> bool:
        return self._idx >= len(self._keys)

    def reset(self) -> None:
        self._idx = 0


class DatalabConvertClient:
    """POST /convert and poll request_check_url until complete."""

    def __init__(
        self,
        keys: Optional[list[str]] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self._keys = KeyRing(keys or load_api_keys())
        self._settings = settings or get_settings()

    def convert(
        self,
        file_bytes: bytes,
        filename: str,
        mode: str,
        output_format: str,
        extras: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run convert; returns final JSON body (status complete)."""
        self._keys.reset()
        last_err: Optional[Exception] = None
        attempts = max(1, self._settings.max_retries)
        for attempt in range(1, attempts + 1):
            try:
                return self._convert_once(
                    file_bytes, filename, mode, output_format, extras
                )
            except DatalabError:
                raise
            except httpx.HTTPStatusError as exc:
                last_err = exc
                code = exc.response.status_code
                if code in RETRY_STATUS:
                    logger.warning(
                        "convert retriable status=%s attempt=%s/%s",
                        code,
                        attempt,
                        attempts,
                    )
                    if len(self._keys) > 1:
                        self._keys.rotate()
                        if self._keys.exhausted():
                            self._keys.reset()
                    if attempt < attempts:
                        continue
                else:
                    raise
            except (httpx.TimeoutException, httpx.NetworkError, TimeoutError) as exc:
                last_err = exc
                logger.warning(
                    "convert retry on timeout/network attempt=%s/%s error=%s",
                    attempt,
                    attempts,
                    exc,
                )
                if attempt < attempts:
                    continue
            except Exception as exc:
                last_err = exc
                logger.exception("convert failed")
                break
        raise DatalabError(str(last_err) if last_err else "convert failed")

    def _convert_once(
        self,
        file_bytes: bytes,
        filename: str,
        mode: str,
        output_format: str,
        extras: Optional[str],
    ) -> Dict[str, Any]:
        url = f"{self._settings.base_url}/convert"
        headers = {"X-API-Key": self._keys.current()}
        data = {
            "mode": mode,
            "output_format": output_format,
        }
        if extras:
            data["extras"] = extras
        timeout = httpx.Timeout(self._settings.http_timeout_sec)
        safe_name = self._safe_filename(filename)
        mime, _ = mimetypes.guess_type(safe_name)
        if not mime:
            mime = "application/octet-stream"
        with httpx.Client(timeout=timeout) as client:
            resp = self._request_with_retry(
                lambda: client.post(
                    url,
                    headers=headers,
                    data=data,
                    files={"file": (safe_name, file_bytes, mime)},
                ),
                action="submit",
                method="POST",
                url=url,
            )
            if resp.status_code >= 400:
                resp.raise_for_status()
            body = resp.json()
        if not body.get("success"):
            raise RuntimeError(f"submit failed: {body}")
        check_url = body["request_check_url"]
        return self._poll(check_url)

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """Sanitize upload name for multipart providers with strict parsing."""
        stripped = (filename or "upload").strip()
        if "." in stripped:
            ext = stripped.rsplit(".", 1)[1].lower()
        else:
            ext = "png"
        base = stripped.rsplit(".", 1)[0]
        base = SAFE_FILENAME_PATTERN.sub("_", base).strip("._-")
        if not base:
            base = "upload"
        return f"{base}.{ext}"

    def _poll(self, check_url: str) -> Dict[str, Any]:
        deadline = time.monotonic() + self._settings.poll_timeout_sec
        timeout = httpx.Timeout(self._settings.http_timeout_sec)
        with httpx.Client(timeout=timeout) as client:
            while time.monotonic() < deadline:
                if self._keys.exhausted():
                    raise DatalabError("API keys exhausted during poll")
                headers = {"X-API-Key": self._keys.current()}
                r = self._request_with_retry(
                    lambda: client.get(check_url, headers=headers),
                    action="poll",
                    method="GET",
                    url=check_url,
                )
                r.raise_for_status()
                result = r.json()
                status = result.get("status")
                if status == "complete":
                    if not result.get("success", True):
                        err = result.get("error", "unknown")
                        raise RuntimeError(f"conversion failed: {err}")
                    return result
                if status == "failed":
                    err = result.get("error", "unknown")
                    raise RuntimeError(f"conversion failed: {err}")
                time.sleep(self._settings.poll_interval_sec)
        raise TimeoutError("poll timeout")

    def _request_with_retry(
        self,
        request_call: Callable[[], httpx.Response],
        action: str,
        method: str,
        url: str,
    ) -> httpx.Response:
        start = time.perf_counter()
        try:
            response = request_call()
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "datalab_request action=%s method=%s url=%s status=%s "
                "duration_ms=%.2f",
                action,
                method,
                url,
                response.status_code,
                elapsed_ms,
            )
            return response
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.warning(
                "datalab_request_error action=%s method=%s url=%s "
                "duration_ms=%.2f error=%s",
                action,
                method,
                url,
                elapsed_ms,
                exc,
            )
            raise
