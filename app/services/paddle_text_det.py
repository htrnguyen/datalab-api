"""Singleton wrapper around PaddleX text detection model."""

from __future__ import annotations

import logging
import time
from io import BytesIO
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from app.core.config import (
    PaddleTextDetSettings,
    get_paddle_text_det_settings,
)

logger = logging.getLogger(__name__)


class PaddleTextDetectorError(RuntimeError):
    """Raised when paddle text detector cannot run."""


def _import_dependencies() -> Tuple[Any, Any]:
    try:
        import numpy as np
        from paddlex import create_model
    except ImportError as exc:
        msg = (
            "paddlex/paddlepaddle not installed; "
            "install paddlepaddle-gpu and paddlex>=3.0"
        )
        raise PaddleTextDetectorError(msg) from exc
    return np, create_model


def _extract_polys_scores(result: Any) -> Tuple[List[Any], List[float]]:
    """Best-effort extract polygons + scores from a paddlex result."""
    polys: Any = None
    scores: Any = None
    try:
        polys = result["dt_polys"]
        scores = result["dt_scores"]
    except (KeyError, TypeError):
        pass
    if polys is None:
        polys = getattr(result, "dt_polys", None) or []
    if scores is None:
        scores = getattr(result, "dt_scores", None) or []
    return list(polys), list(scores)


def _polygon_to_int(poly: Any) -> List[List[int]]:
    out: List[List[int]] = []
    for point in poly:
        x, y = float(point[0]), float(point[1])
        out.append([int(round(x)), int(round(y))])
    return out


def _polygon_bbox(points: List[List[int]]) -> List[int]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


class PaddleTextDetector:
    """Loads the paddle model once and serves predictions."""

    _instance: Optional["PaddleTextDetector"] = None
    _lock: Lock = Lock()

    def __init__(self, settings: PaddleTextDetSettings) -> None:
        self._settings = settings
        self._np, create_model = _import_dependencies()
        self._model = self._build_model(create_model)

    def _build_model(self, create_model: Any) -> Any:
        kwargs: Dict[str, Any] = {
            "model_name": self._settings.model_name,
            "device": self._settings.device,
        }
        if self._settings.model_dir:
            kwargs["model_dir"] = self._settings.model_dir
        logger.info(
            "loading paddle_text_det name=%s dir=%s device=%s",
            self._settings.model_name,
            self._settings.model_dir,
            self._settings.device,
        )
        return create_model(**kwargs)

    @classmethod
    def get(cls) -> "PaddleTextDetector":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(get_paddle_text_det_settings())
        return cls._instance

    @classmethod
    def warm_up(cls) -> None:
        """Force load the singleton; raises on failure."""
        cls.get()

    def predict_bytes(
        self,
        raw: bytes,
        filename: str,
    ) -> Dict[str, Any]:
        """Run detection on a single image given as raw bytes."""
        image = Image.open(BytesIO(raw)).convert("BGR")
        arr = self._np.array(image)
        start = time.perf_counter()
        results = list(self._model.predict(arr, batch_size=1))
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "paddle_text_det predict file=%s duration_ms=%.2f",
            filename,
            elapsed_ms,
        )
        detections = self._build_detections(results)
        return {
            "width": image.width,
            "height": image.height,
            "detections": detections,
        }

    @staticmethod
    def _build_detections(results: List[Any]) -> List[Dict[str, Any]]:
        if not results:
            return []
        polys, scores = _extract_polys_scores(results[0])
        items: List[Dict[str, Any]] = []
        for poly, score in zip(polys, scores):
            poly_int = _polygon_to_int(poly)
            if not poly_int:
                continue
            items.append(
                {
                    "polygon": poly_int,
                    "bbox": _polygon_bbox(poly_int),
                    "score": float(score),
                }
            )
        return items
