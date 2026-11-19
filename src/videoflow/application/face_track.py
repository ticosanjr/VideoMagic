"""Single-frame face detection for crop previews and framing decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def detect_face_bbox(image_path: str | Path) -> dict[str, Any] | None:
    """Return the largest face bbox in source pixels and normalized centers."""

    path = Path(image_path).expanduser()
    if not path.is_file():
        return None
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - optional dependency
        return None
    image = cv2.imread(str(path))
    if image is None:
        return None
    height, width = image.shape[:2]
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(str(cascade_path))
    if detector.empty():
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
    if not len(faces):
        return None
    x, y, face_w, face_h = max(
        faces, key=lambda item: int(item[2]) * int(item[3])
    )
    return {
        "x": int(x),
        "y": int(y),
        "w": int(face_w),
        "h": int(face_h),
        "center_x": int(x + face_w / 2),
        "center_y": int(y + face_h / 2),
        "center_x_norm": round((x + face_w / 2) / max(1, width), 6),
        "center_y_norm": round((y + face_h / 2) / max(1, height), 6),
    }


__all__ = ["detect_face_bbox"]
