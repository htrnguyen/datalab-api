"""FastAPI entrypoint."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api.routes.ocr import router as ocr_router
from app.api.routes.text_detection import router as text_det_router
from app.core.config import get_paddle_text_det_settings
from app.services.paddle_text_det import (
    PaddleTextDetector,
    PaddleTextDetectorError,
)

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Warm up heavy ML resources on startup."""
    settings = get_paddle_text_det_settings()
    if settings.eager_load:
        try:
            await asyncio.to_thread(PaddleTextDetector.warm_up)
            logger.info(
                "paddle_text_det warm_up ok name=%s device=%s",
                settings.model_name,
                settings.device,
            )
        except PaddleTextDetectorError:
            logger.exception("paddle_text_det warm_up failed")
            raise
    yield


app = FastAPI(
    title="Datalab OCR Service",
    version="0.2.0",
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
app.include_router(text_det_router)


@app.middleware("http")
async def log_request_timing(request: Request, call_next) -> Response:
    """Log each incoming API request with duration and errors."""
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "request_error method=%s path=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise


@app.get("/")
def root() -> dict[str, str]:
    """Root endpoint for quick service check."""
    return {
        "service": "datalab-ocr",
        "status": "ok",
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Service health endpoint."""
    return {"status": "ok"}
