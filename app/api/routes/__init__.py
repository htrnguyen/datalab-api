"""API routes."""

from app.api.routes.ocr import router as ocr_router
from app.api.routes.storage import router as storage_router

__all__ = ["ocr_router", "storage_router"]
