"""Async HTTP client for Datalab extraction API."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 2
POLL_MAX_ATTEMPTS = 300
SCORE_POLL_ATTEMPTS = 30


class ExtractionClientError(Exception):
    """Base exception for extraction client errors."""
    pass


class ExtractionTimeoutError(ExtractionClientError):
    """Raised when polling times out."""
    pass


class ExtractionFailedError(ExtractionClientError):
    """Raised when extraction job fails."""
    pass


class ExtractionSubmitError(ExtractionClientError):
    """Raised when submission fails."""
    pass


class ExtractionClient:
    """Async HTTP client for Datalab extraction API.

    Thread-safe singleton with connection pooling and API key rotation.
    Each job maintains the same API key from submit to poll completion.
    Keys are validated on initialization.
    """

    _instances: dict[int, "ExtractionClient"] = {}
    _class_lock = asyncio.Lock()

    def __new__(cls, settings: Settings) -> "ExtractionClient":
        pid = id(settings)
        if pid not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[pid] = instance
        return cls._instances[pid]

    def __init__(self, settings: Settings):
        if hasattr(self, "_initialized") and self._settings is settings:
            return
        self._settings = settings
        self._http: httpx.AsyncClient | None = None
        self._api_keys: list[str] = []
        self._key_index = 0
        self._key_lock = asyncio.Lock()
        self._initialized = True

    async def initialize(self) -> None:
        """Load and validate API keys on startup.

        Call this method after creating the client.
        """
        from app.core.config import load_and_validate_api_keys
        self._api_keys = await load_and_validate_api_keys()
        logger.info("ExtractionClient initialized with %d valid API keys", len(self._api_keys))

    async def _get_api_key(self) -> str:
        """Get next API key using round-robin rotation."""
        if not self._api_keys:
            await self.initialize()

        async with self._key_lock:
            key = self._api_keys[self._key_index]
            self._key_index = (self._key_index + 1) % len(self._api_keys)
            return key

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client with connection pooling."""
        if self._http is None or self._http.is_closed:
            timeout = httpx.Timeout(
                connect=10.0,
                write=self._settings.http_timeout_sec,
                read=self._settings.http_timeout_sec,
                pool=10.0,
            )
            limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
            self._http = httpx.AsyncClient(timeout=timeout, limits=limits)
        return self._http

    async def aclose(self) -> None:
        """Close the HTTP client."""
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    @classmethod
    async def shutdown_all(cls) -> None:
        """Close all client instances. Call on app shutdown."""
        async with cls._class_lock:
            for instance in cls._instances.values():
                await instance.aclose()
            cls._instances.clear()

    async def submit(
        self,
        file_bytes: bytes,
        filename: str,
        schema_json: str,
        request_id: str,
    ) -> tuple[dict, str]:
        """Submit file with schema to Datalab API.

        Returns:
            Tuple of (result dict, api_key used)

        Raises:
            ExtractionSubmitError: If submission fails
        """
        api_key = await self._get_api_key()
        request_headers = {"X-Api-Key": api_key} if api_key else None
        url = f"{self._settings.base_url}/marker"

        logger.info("[%s] Submitting to %s (key_idx=%d)", request_id, url, self._key_index - 1)

        client = await self._get_client()
        resp = await client.post(
            url,
            headers=request_headers,
            files={
                "file": (filename, file_bytes, "application/pdf"),
                "page_schema": (None, schema_json),
            },
        )

        if resp.status_code != 200:
            raise ExtractionSubmitError(
                f"Submit failed: {resp.status_code} — {resp.text[:200]}"
            )

        data = resp.json()
        if not data.get("success"):
            raise ExtractionSubmitError(f"Submit failed: {data}")

        return data, api_key

    async def poll(
        self,
        check_url: str,
        request_id: str,
        api_key: str,
        timeout_sec: float | None = None,
    ) -> dict:
        """Poll check_url until extraction completes or fails.

        Args:
            check_url: URL to poll for status
            request_id: For logging
            api_key: API key from submit (MUST be same key!)
            timeout_sec: Override poll timeout (uses settings if None)

        Returns:
            Complete result dict

        Raises:
            ExtractionFailedError: If job fails
            ExtractionTimeoutError: If polling times out
        """
        timeout = timeout_sec or self._settings.poll_timeout_sec
        request_headers = {"X-Api-Key": api_key} if api_key else None

        deadline = time.monotonic() + timeout

        for i in range(POLL_MAX_ATTEMPTS):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ExtractionTimeoutError(
                    f"[{request_id}] Polling timed out after {timeout}s"
                )

            await asyncio.sleep(min(POLL_INTERVAL_SEC, remaining))

            client = await self._get_client()
            r = await client.get(check_url, headers=request_headers)

            if r.status_code == 403:
                logger.warning("[%s] Poll %d HTTP 403 - key mismatch?", request_id, i + 1)
                continue

            if r.status_code != 200:
                logger.warning("[%s] Poll %d HTTP %d", request_id, i + 1, r.status_code)
                continue

            d = r.json()
            status = d.get("status")
            logger.debug("[%s] Poll %d status=%s", request_id, i + 1, status)

            if status == "failed":
                raise ExtractionFailedError(
                    f"[{request_id}] Job failed: {d.get('error', 'unknown')}"
                )

            if status == "complete":
                return await self._fetch_score_average(check_url, request_headers, d, request_id)

        raise ExtractionTimeoutError(
            f"[{request_id}] Polling timed out after {POLL_MAX_ATTEMPTS} attempts"
        )

    async def _fetch_score_average(
        self,
        check_url: str,
        headers: dict | None,
        result: dict,
        request_id: str,
    ) -> dict:
        """Poll for extraction_score_average after completion."""
        score_avg = None

        for _ in range(SCORE_POLL_ATTEMPTS):
            await asyncio.sleep(POLL_INTERVAL_SEC)

            client = await self._get_client()
            sr = await client.get(check_url, headers=headers)

            if sr.status_code == 200:
                score_avg = sr.json().get("extraction_score_average")
                if score_avg is not None:
                    result["_score_avg"] = score_avg
                    break

        if score_avg is None:
            logger.debug("[%s] extraction_score_average not found", request_id)

        return result

    async def submit_and_poll(
        self,
        file_bytes: bytes,
        filename: str,
        schema_json: str,
        schema_name: str,
        request_id: str,
    ) -> dict:
        """Submit file and poll for result.

        IMPORTANT: Same API key is used for both submit and poll.

        Args:
            file_bytes: File content
            filename: Original filename
            schema_json: JSON schema string
            schema_name: Schema identifier
            request_id: For logging

        Returns:
            Complete result dict
        """
        logger.info("[%s/%s] Starting extraction", request_id, schema_name)

        # Submit and get the API key used
        submit_result, api_key = await self.submit(file_bytes, filename, schema_json, request_id)
        check_url = submit_result.get("request_check_url")
        logger.info("[%s/%s] Polling: %s", request_id, schema_name, check_url)

        # Poll using the SAME API key
        return await self.poll(check_url, request_id, api_key)
