from __future__ import annotations

import logging
import os
import platform
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.routes.ocr import get_limiter, router as ocr_router
from app.api.routes.extraction import router as extraction_router

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)
_tz_utc7 = timedelta(hours=7)


class _UTC7Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc) + _tz_utc7
        return dt.strftime(datefmt or "%Y-%m-%d %H:%M:%S")


for _handler in logging.root.handlers:
    _handler.setFormatter(
        _UTC7Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"
        )
    )
logger = logging.getLogger(__name__)

# Suppress verbose httpx/httpcore poll logs (only show errors)
for _lib in ("httpx", "httpcore"):
    _l = logging.getLogger(_lib)
    _l.setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting OCR service...")
    logger.info("validating API keys...")
    try:
        from app.api.routes.extraction import _get_client

        await _get_client()
        logger.info("API key validation complete")
    except Exception as e:
        logger.error("API key validation failed: %s", e)
    yield
    logger.info("shutting down OCR service...")
    from app.api.routes.ocr import _get_async_client

    await _get_async_client().aclose()
    from app.services.extraction_client import ExtractionClient

    await ExtractionClient.shutdown_all()
    logger.info("shutdown complete")


app = FastAPI(
    title="OCR Service",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ocr_router)
app.include_router(extraction_router)


@app.middleware("http")
async def log_request_timing(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "method=%s path=%s status=%d duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "method=%s path=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    python_version: str
    platform: str
    requests: dict


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        limiter_stats = get_limiter().get_stats()
    except Exception:
        limiter_stats = {"error": "limiter not initialized"}

    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="1.0.0",
        python_version=platform.python_version(),
        platform=platform.platform(),
        requests=limiter_stats,
    )


class InfoResponse(BaseModel):
    service: str
    version: str
    docs: str
    health: str
    usage: dict


@app.get("/", response_model=InfoResponse)
def root() -> InfoResponse:
    return InfoResponse(
        service="OCR Service",
        version="1.0.0",
        docs="/docs",
        health="/health",
        usage={
            "endpoints": {
                "ocr": {
                    "method": "POST",
                    "path": "/api/v1/ocr",
                    "params": {
                        "mode": "fast | balanced | accurate (default: accurate)",
                        "infographic": "true | false (default: false)",
                    },
                    "file_types": "PNG, JPG, WEBP, PDF",
                    "examples": [
                        {
                            "description": "Basic OCR (accurate mode)",
                            "curl": (
                                "curl -X POST 'http://localhost:4242/api/v1/ocr?mode=accurate&infographic=false' "
                                "-H 'accept: application/json' "
                                "-H 'Content-Type: multipart/form-data' "
                                "-F 'file=@image.png;type=image/png'"
                            ),
                        },
                        {
                            "description": "Fast mode",
                            "curl": (
                                "curl -X POST 'http://localhost:4242/api/v1/ocr?mode=fast' "
                                "-F 'file=@document.pdf'"
                            ),
                        },
                        {
                            "description": "Infographic mode for diagrams",
                            "curl": (
                                "curl -X POST 'http://localhost:4242/api/v1/ocr?mode=accurate&infographic=true' "
                                "-F 'file=@diagram.png'"
                            ),
                        },
                    ],
                },
                "stats": {
                    "method": "GET",
                    "path": "/api/v1/ocr/stats",
                    "description": "Get rate limiter statistics",
                },
                "extraction": {
                    "method": "POST",
                    "path": "/api/v1/extraction",
                    "params": {
                        "file": "PDF file (required)",
                        "schemas": 'JSON array [{"name":"...","schema":"..."}] (required)',
                        "name": "Submission ID override (optional)",
                    },
                    "file_types": "PDF",
                    "examples": [
                        {
                            "description": "Single or multiple schema extraction",
                            "curl": (
                                "curl -X POST 'http://localhost:4242/api/v1/extraction' "
                                "-F 'file=@document.pdf' "
                                '-F \'schemas=[{"name":"criteria","schema":"{\\"type\\":\\"object\\"}"}]\''
                            ),
                        },
                    ],
                },
                "health": {
                    "method": "GET",
                    "path": "/health",
                    "description": "Health check",
                },
            },
        },
    )


@app.exception_handler(404)
def not_found(_request: Request, _exc):
    return JSONResponse({"detail": "Not Found"}, status_code=404)


@app.exception_handler(500)
def internal_error(request: Request, exc: Exception):
    logger.exception("internal_error path=%s", request.url.path)
    return JSONResponse(
        {"detail": "Internal server error"},
        status_code=500,
    )
