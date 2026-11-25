"""Face detection for crop previews and Short framing decisions."""

from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any


def _haar_detector() -> Any | None:
    """Load the frontal-face Haar cascade when the OpenCV build ships one."""

    try:
        import cv2  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - optional dependency
        return None
    classifier = getattr(cv2, "CascadeClassifier", None)
    if classifier is None:  # OpenCV 5 builds may omit the legacy cascade API
        return None
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    detector = classifier(str(cascade_path))
    return None if detector.empty() else detector


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
    detector = _haar_detector()
    if detector is None:
        return None
    height, width = image.shape[:2]
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


def _sample_video_frames(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    *,
    samples: int,
) -> list[Any]:
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - optional dependency
        return []
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return []
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    span = max(0.001, float(end_sec) - float(start_sec))
    frames: list[Any] = []
    try:
        for index in range(max(1, int(samples))):
            timestamp = float(start_sec) + span * (index + 0.5) / max(1, int(samples))
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
            ok, frame = capture.read()
            if not ok and fps > 0:
                capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(timestamp * fps)))
                ok, frame = capture.read()
            if ok and frame is not None:
                frames.append(frame)
    finally:
        capture.release()
    return frames


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _mediapipe_centers(frames: list[Any]) -> list[tuple[float, float]]:
    try:
        import cv2  # type: ignore[import-not-found]
        import mediapipe as mp  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - mediapipe is optional
        return []
    centers: list[tuple[float, float]] = []
    try:
        with mp.solutions.face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=0.5,
        ) as detector:
            for frame in frames:
                result = detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                detections = getattr(result, "detections", None) or []
                if not detections:
                    continue
                best = max(
                    detections,
                    key=lambda item: float(
                        item.location_data.relative_bounding_box.width
                    )
                    * float(item.location_data.relative_bounding_box.height),
                )
                box = best.location_data.relative_bounding_box
                centers.append(
                    (
                        _clamp(box.xmin + box.width / 2),
                        _clamp(box.ymin + box.height / 2),
                    )
                )
    except Exception:  # noqa: BLE001 - any backend failure falls back to Haar
        return []
    return centers


def _haar_centers(frames: list[Any]) -> list[tuple[float, float]]:
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - optional dependency
        return []
    detector = _haar_detector()
    if detector is None:
        return []
    centers: list[tuple[float, float]] = []
    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape[:2]
        min_size = (max(24, width // 20), max(24, height // 20))
        candidates: list[tuple[int, int, int, int]] = []
        for scale in (1.05, 1.1, 1.2):
            try:
                faces = detector.detectMultiScale(
                    gray,
                    scaleFactor=scale,
                    minNeighbors=4,
                    minSize=min_size,
                )
            except Exception:  # noqa: BLE001 - one scale must not abort the scan
                faces = ()
            candidates.extend(tuple(int(value) for value in face) for face in faces)
        # Medium shots often crop the forehead; retry the upper-central 70%.
        left = int(width * 0.15)
        right = max(left + 1, int(width * 0.85))
        bottom = max(1, int(height * 0.70))
        upper = gray[0:bottom, left:right]
        for scale in (1.05, 1.1):
            try:
                faces = detector.detectMultiScale(
                    upper,
                    scaleFactor=scale,
                    minNeighbors=4,
                    minSize=(min_size[0] // 2, min_size[1] // 2),
                )
            except Exception:  # noqa: BLE001
                faces = ()
            candidates.extend(
                (int(x) + left, int(y), int(w), int(h)) for x, y, w, h in faces
            )
        if not candidates:
            continue
        x, y, face_w, face_h = max(
            candidates, key=lambda item: item[2] * item[3]
        )
        centers.append(
            (
                _clamp((x + face_w / 2) / max(1, width)),
                _clamp((y + face_h / 2) / max(1, height)),
            )
        )
    return centers


def detect_face_median_x(
    video_path: str | Path,
    start_sec: float,
    end_sec: float,
    *,
    samples: int = 7,
) -> dict[str, Any]:
    """Median face center across sampled frames of one clip.

    MediaPipe (long-range model) runs first; OpenCV Haar then scans the full
    frame and an upper-central crop at three scales, which recovers faces in
    medium shots where the default detector misses. No detection is reported
    explicitly with ``face_fallback_center=True``.
    """

    path = Path(video_path).expanduser()
    requested = max(1, int(samples))
    frames = _sample_video_frames(path, start_sec, end_sec, samples=requested)
    backend = "none"
    centers: list[tuple[float, float]] = []
    if frames:
        centers = _mediapipe_centers(frames)
        if centers:
            backend = "mediapipe"
        else:
            centers = _haar_centers(frames)
            if centers:
                backend = "opencv-haar"
    cx = round(float(median([item[0] for item in centers])), 6) if centers else None
    cy = round(float(median([item[1] for item in centers])), 6) if centers else None
    return {
        "cx_median": cx,
        "cy_median": cy,
        "detections": len(centers),
        "samples": len(frames),
        "backend": backend,
        "face_fallback_center": not bool(centers),
    }


__all__ = ["detect_face_bbox", "detect_face_median_x"]
