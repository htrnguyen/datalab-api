import asyncio
import logging
import mimetypes
import re
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from app.core.config import Settings, get_settings
from app.schemas.ocr import OCRResponse
from app.services.datalab_client import DatalabClient, DatalabError
from app.services.ocr_service import OCRService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ocr", tags=["ocr"])

VALID_MODES = {"fast", "balanced", "accurate"}
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(fn: str) -> str:
    base = (fn or "upload").strip()
    ext = "png"
    if "." in base:
        base, ext = base.rsplit(".", 1)
        ext = ext.lower()
    base = SAFE_FILENAME_RE.sub("_", base).strip("._-") or "upload"
    ext = SAFE_FILENAME_RE.sub("_", ext) or "png"
    return f"{base}.{ext}"


def _get_extension(filename: str | None) -> str:
    if not filename:
        return ""
    ext = Path(filename).suffix.lower().lstrip(".")
    return ext


class RequestLimiter:
    def __init__(self, max_concurrent: int = 5):
        self._max = max_concurrent
        self._active = 0
        self._lock = asyncio.Lock()
        self._total_requests = 0
        self._total_rejected = 0

    async def acquire(self) -> tuple[bool, float]:
        self._total_requests += 1
        wait_start = time.perf_counter()

        async with self._lock:
            if self._active >= self._max:
                self._total_rejected += 1
                return False, 0.0
            self._active += 1
            wait_time = time.perf_counter() - wait_start
            return True, wait_time

    async def release(self) -> None:
        async with self._lock:
            self._active = max(0, self._active - 1)

    def get_stats(self) -> dict:
        return {
            "active": self._active,
            "max": self._max,
            "total_requests": self._total_requests,
            "total_rejected": self._total_rejected,
        }


_limiter: RequestLimiter | None = None


def get_limiter() -> RequestLimiter:
    global _limiter
    if _limiter is None:
        settings = get_settings()
        _limiter = RequestLimiter(max_concurrent=settings.max_concurrent_requests)
    return _limiter


class AsyncDatalabClient(DatalabClient):
    async def convert_async(
        self,
        file_bytes: bytes,
        filename: str,
        mode: str = "accurate",
        output_format: str = "json",
        extras: str | None = None,
        mime: str | None = None,
    ) -> dict:
        self._key_idx = 0
        max_retries = max(1, self._settings.max_retries)
        last_err: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                return await self._convert_once_async(
                    file_bytes,
                    _safe_filename(filename),
                    mode,
                    output_format,
                    extras,
                    mime,
                )
            except httpx.HTTPStatusError as exc:
                last_err = exc
                if (
                    exc.response.status_code in {401, 403, 429}
                    and attempt < max_retries
                ):
                    self._rotate()
                    await asyncio.sleep(min(8.0, 2**attempt))
                    continue
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_err = exc
                if attempt < max_retries:
                    await asyncio.sleep(min(8.0, 2**attempt))
                    continue
            except Exception as exc:
                logger.exception("convert_async failed")
                raise DatalabError(str(exc)) from exc

        raise DatalabError(str(last_err) if last_err else "convert failed")

    async def _convert_once_async(
        self,
        file_bytes: bytes,
        filename: str,
        mode: str,
        output_format: str,
        extras: str | None,
        mime: str | None,
    ) -> dict:
        url = f"{self._settings.base_url}/convert"

        if mime:
            final_mime = mime
        else:
            final_mime, _ = mimetypes.guess_type(filename)
            if not final_mime:
                final_mime = "application/octet-stream"

        data: dict = {"mode": mode, "output_format": output_format}
        if extras:
            data["extras"] = extras

        http = await self._get_async_client()
        resp = await http.post(
            url,
            headers={"X-API-Key": self._current_key},
            data=data,
            files={"file": (filename, file_bytes, final_mime)},
        )

        if resp.status_code >= 400:
            logger.error("Datalab error %d: %s", resp.status_code, resp.text[:300])
            resp.raise_for_status()

        body = resp.json()
        if not body.get("success"):
            raise DatalabError(f"Datalab submit failed: {body}")

        return await self._poll_async(body["request_check_url"])

    async def _poll_async(self, check_url: str) -> dict:
        deadline = time.monotonic() + self._settings.poll_timeout_sec
        http = await self._get_async_client()

        while time.monotonic() < deadline:
            resp = await http.get(check_url, headers={"X-API-Key": self._current_key})
            resp.raise_for_status()
            result = resp.json()

            status = result.get("status")
            if status == "complete":
                if not result.get("success", True):
                    raise DatalabError(f"Conversion failed: {result.get('error', 'unknown')}")
                return result
            if status == "failed":
                raise DatalabError(f"Conversion failed: {result.get('error', 'unknown')}")

            await asyncio.sleep(self._settings.poll_interval_sec)

        raise DatalabError("Conversion timed out")

    async def _get_async_client(self) -> httpx.AsyncClient:
        if not hasattr(self, "_async_http") or self._async_http.is_closed:
            timeout = httpx.Timeout(
                connect=10.0,
                write=self._settings.http_timeout_sec,
                read=self._settings.http_timeout_sec,
                pool=10.0,
            )
            limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
            self._async_http = httpx.AsyncClient(timeout=timeout, limits=limits)
        return self._async_http

    async def aclose(self) -> None:
        if hasattr(self, "_async_http"):
            await self._async_http.aclose()
            del self._async_http


class AsyncOCRService(OCRService):
    def __init__(self, client: AsyncDatalabClient):
        super().__init__(client)

    async def process_async(
        self,
        file_bytes: bytes,
        filename: str,
        mode: str = "accurate",
        infographic: bool = False,
        request_id: str | None = None,
    ) -> OCRResponse:
        settings = get_settings()
        size_bytes = len(file_bytes)
        size_mb = size_bytes / (1024 * 1024)

        logger.info(
            "ocr_process_start request_id=%s filename=%s size_bytes=%s size_mb=%.3f mode=%s infographic=%s",
            request_id,
            filename,
            size_bytes,
            size_mb,
            mode,
            infographic,
        )

        start = time.perf_counter()
        try:
            result = await self._client.convert_async(
                file_bytes=file_bytes,
                filename=filename,
                mode=mode,
                output_format="json",
                extras="infographic" if infographic else None,
                mime=None,
            )
        except Exception as exc:
            logger.exception("ocr_datalab_failed request_id=%s filename=%s", request_id, filename)
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "ocr_datalab_done request_id=%s filename=%s elapsed_ms=%.2f",
            request_id,
            filename,
            elapsed_ms,
        )

        try:
            response = self._transform_response(result, file_bytes)
        except Exception as exc:
            logger.exception("ocr_transform_failed request_id=%s filename=%s", request_id, filename)
            raise

        total_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "ocr_done request_id=%s filename=%s page_count=%s block_count=%s total_ms=%.2f",
            request_id,
            filename,
            response.page_count,
            sum(len(page.blocks) for page in response.pages),
            total_ms,
        )

        if settings.debug_log_enabled:
            try:
                self._save_debug_payload(request_id, filename, mode, infographic, result, response)
            except Exception as exc:
                logger.debug("ocr_debug_save_failed request_id=%s: %s", request_id, exc)

        return response


@lru_cache
def _get_async_client() -> AsyncDatalabClient:
    return AsyncDatalabClient()


def _get_async_service() -> AsyncOCRService:
    return AsyncOCRService(client=_get_async_client())


def get_ocr_service() -> AsyncOCRService:
    return _get_async_service()


@router.post("", summary="Process OCR", response_model=OCRResponse)
async def process_ocr(
    request: Request,
    file: Annotated[UploadFile, File(description="Image (PNG, JPG, WEBP) or PDF file")],
    mode: Annotated[
        str,
        Query(description="Processing mode: fast, balanced, or accurate"),
    ] = "accurate",
    infographic: Annotated[
        bool,
        Query(description="Enable infographic mode"),
    ] = False,
    service: AsyncOCRService = Depends(get_ocr_service),
) -> OCRResponse:
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
    settings = get_settings()
    limiter = get_limiter()

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")

    size_mb = len(raw) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f}MB). Max: {settings.max_upload_size_mb:.0f}MB",
        )

    ext = _get_extension(file.filename)
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: .{ext}. Allowed: {', '.join(sorted(settings.allowed_extensions))}",
        )

    if mode not in VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {mode}. Must be one of: {', '.join(VALID_MODES)}",
        )

    acquired, wait_time = await limiter.acquire()
    if not acquired:
        raise HTTPException(
            status_code=429,
            detail="Server busy. Too many concurrent requests. Please try again.",
        )
    if wait_time > 0.1:
        logger.warning("request_wait request_id=%s wait_s=%.2f", request_id, wait_time)

    try:
        result = await service.process_async(
            file_bytes=raw,
            filename=file.filename or "upload",
            mode=mode,
            infographic=infographic,
            request_id=request_id,
        )
        return result
    except DatalabError as exc:
        logger.error("OCR DatalabError request_id=%s: %s", request_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("OCR processing failed request_id=%s", request_id)
        raise HTTPException(
            status_code=500,
            detail="OCR processing failed. Please try again or contact support.",
        ) from exc
    finally:
        await limiter.release()
