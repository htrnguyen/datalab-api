"""FastAPI entrypoint for OCR service."""

from __future__ import annotations

import logging
import os
import platform
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.routes.ocr import get_limiter, router as ocr_router

# Load .env file if it exists
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown."""
    logger.info("starting OCR service...")
    yield
    logger.info("shutting down OCR service...")
    from app.api.routes.ocr import _get_async_client
    await _get_async_client().aclose()
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
    """Health check endpoint with system info."""
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


@app.get("/")
def root() -> dict:
    """Root endpoint with API info."""
    return {
        "service": "OCR Service",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


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
