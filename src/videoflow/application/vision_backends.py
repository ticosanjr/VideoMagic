"""Optional vision backend discovery and policy.

MediaPipe, Ultralytics YOLO, OpenCV, and WhisperX are optional. Import them
lazily so a base install keeps working without the tracking/alignment extras.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

TRACKING_BACKENDS = ("auto", "mediapipe", "yolo", "opencv_haar", "motion_tracking")


def _available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def mediapipe_available() -> bool:
    return _available("mediapipe")


def opencv_available() -> bool:
    return _available("cv2")


def yolo_available(model_path: str = "") -> bool:
    path = yolo_model_path(model_path)
    return bool(path) and _available("ultralytics")


def yolo_model_path(explicit: str = "") -> str:
    value = explicit.strip()
    if not value:
        value = os.environ.get("VIDEOWFLOW_YOLO_MODEL", "").strip()
    if not value:
        try:
            from videoflow.application.settings import load_settings

            value = load_settings().vision.yolo_model.strip()
        except Exception:  # noqa: BLE001 - settings are advisory
            value = ""
    if not value:
        return ""
    path = Path(value).expanduser()
    return str(path) if path.is_file() else ""


def mediapipe_model_selection(explicit: int = 1) -> int:
    return 0 if int(explicit) == 0 else 1


def resolve_tracking_backend(
    requested: str,
    mode: str,
    *,
    yolo_model: str = "",
    settings: Any | None = None,
) -> tuple[str, str]:
    """Return ``(backend, reason)`` where backend is the concrete implementation."""

    try:
        from videoflow.application.settings import load_settings

        vision = (settings or load_settings()).vision
    except Exception:  # noqa: BLE001
        vision = None
    preferred = (requested or "auto").strip().lower()
    if preferred == "auto" and vision is not None:
        preferred = getattr(vision, "tracking_backend", "auto")
    if preferred == "auto":
        if mode == "motion_tracking":
            return "motion_tracking", "motion mode"
        if mediapipe_available():
            return "mediapipe", "mediapipe detected"
        if yolo_available(yolo_model or (getattr(vision, "yolo_model", "") if vision else "")):
            return "yolo", "yolo model detected"
        if opencv_available():
            return "opencv_haar", "opencv detected"
        return "motion_tracking", "no face backend available"

    if preferred == "mediapipe":
        if mediapipe_available():
            return "mediapipe", "requested mediapipe"
        return "motion_tracking", "mediapipe is not installed"
    if preferred == "yolo":
        if yolo_available(yolo_model or (getattr(vision, "yolo_model", "") if vision else "")):
            return "yolo", "requested yolo"
        return "motion_tracking", "yolo/ultralytics or model is unavailable"
    if preferred in {"opencv_haar", "opencv"}:
        if opencv_available():
            return "opencv_haar", "requested opencv"
        return "motion_tracking", "opencv is not installed"
    if preferred in {"motion", "motion_tracking"}:
        return "motion_tracking", "requested motion"
    return "motion_tracking", f"unknown tracking backend: {requested}"


__all__ = [
    "TRACKING_BACKENDS",
    "mediapipe_available",
    "mediapipe_model_selection",
    "opencv_available",
    "resolve_tracking_backend",
    "yolo_available",
    "yolo_model_path",
]
