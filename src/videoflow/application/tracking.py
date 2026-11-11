"""Lightweight Short reframing focus estimation.

Motion tracking uses FFmpeg-decoded low-resolution frames and NumPy. Face
tracking is optional and only activates when OpenCV is installed.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from videoflow.domain.errors import IngestError
from videoflow.runtime import find_binary


def focus_x_from_frames(frames: np.ndarray) -> float:
    if frames.ndim != 3 or frames.shape[0] < 2:
        return 0.5
    values = frames.astype(np.int16)
    difference = np.abs(np.diff(values, axis=0))
    mask = difference > 18
    weights = mask.sum(axis=(0, 1)).astype(np.float64)
    if weights.sum() <= 0:
        return 0.5
    x = np.arange(len(weights), dtype=np.float64)
    centroid = float((weights * x).sum() / weights.sum())
    return max(0.05, min(0.95, centroid / max(1, len(weights) - 1)))


def _face_centers(frames: np.ndarray) -> list[float | None]:
    if len(frames) == 0:
        return []
    import cv2  # type: ignore[import-not-found]

    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(str(cascade_path))
    centers: list[float | None] = []
    for frame in frames:
        faces = detector.detectMultiScale(frame, scaleFactor=1.1, minNeighbors=4)
        if not len(faces):
            centers.append(None)
            continue
        x, _y, width, _height = max(
            faces, key=lambda item: int(item[2]) * int(item[3])
        )
        centers.append((x + width / 2) / max(1, frame.shape[1]))
    return centers


def _face_centers_mediapipe(frames: np.ndarray) -> list[float | None]:
    import mediapipe as mp  # type: ignore[import-not-found]

    detector = mp.solutions.face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=0.4
    )
    centers: list[float | None] = []
    try:
        for frame in frames:
            rgb = np.stack([frame] * 3, axis=-1)
            result = detector.process(rgb)
            detections = result.detections or []
            if not detections:
                centers.append(None)
                continue
            best = max(
                detections,
                key=lambda item: float(
                    item.location_data.relative_bounding_box.width
                )
                * float(item.location_data.relative_bounding_box.height),
            )
            box = best.location_data.relative_bounding_box
            centers.append(float(box.xmin + box.width / 2))
    finally:
        detector.close()
    return centers


def _face_centers_yolo(frames: np.ndarray) -> list[float | None]:
    import os

    from ultralytics import YOLO  # type: ignore[import-not-found]

    model_path = os.environ.get("VIDEOWFLOW_YOLO_MODEL", "yolov8n.pt")
    model = YOLO(model_path)
    centers: list[float | None] = []
    for frame in frames:
        rgb = np.stack([frame] * 3, axis=-1)
        results = model.predict(rgb, verbose=False)
        boxes = []
        for result in results:
            for box in getattr(result, "boxes", []) or []:
                cls = int(box.cls[0]) if getattr(box, "cls", None) is not None else 0
                if cls != 0:
                    continue
                x1, _y1, x2, _y2 = [float(value) for value in box.xyxy[0]]
                boxes.append((x2 - x1, (x1 + x2) / 2))
        if not boxes:
            centers.append(None)
            continue
        _width, center = max(boxes, key=lambda item: item[0])
        centers.append(center / max(1, frame.shape[1]))
    return centers


def _motion_centers(frames: np.ndarray) -> list[float | None]:
    if len(frames) < 2:
        return [None for _ in range(len(frames))]
    values = frames.astype(np.int16)
    difference = np.abs(np.diff(values, axis=0))
    mask = difference > 18
    centers: list[float | None] = [None]
    for index in range(mask.shape[0]):
        weights = mask[index].sum(axis=0).astype(np.float64)
        if weights.sum() <= 0:
            centers.append(None)
            continue
        x = np.arange(len(weights), dtype=np.float64)
        centroid = float((weights * x).sum() / weights.sum())
        centers.append(centroid / max(1, len(weights) - 1))
    return centers


def track_focus_keyframes(
    source: Path,
    pieces: Sequence[tuple[int, int]],
    sample_rate: int,
    *,
    mode: str = "motion_tracking",
    smoothing: float = 0.85,
    fps: int = 2,
    backend: str = "",
) -> tuple[list[dict[str, float]], str]:
    """Return a smoothed focus path for dynamic reframing."""

    wide = backend in {"mediapipe", "yolo"}
    frames = frames_from_pieces(
        source,
        pieces,
        sample_rate,
        fps=fps,
        width=256 if wide else 64,
        height=144 if wide else 36,
    )
    if len(frames) == 0:
        return [{"time_sec": 0.0, "focus_x": 0.5}], "motion_tracking"
    values: list[float | None] = []
    used_mode = "motion_tracking"
    if backend == "mediapipe":
        try:
            values = _face_centers_mediapipe(frames)
            used_mode = "mediapipe"
        except ImportError:
            values = []
    elif backend == "yolo":
        try:
            values = _face_centers_yolo(frames)
            used_mode = "yolo"
        except ImportError:
            values = []
    elif mode in {"face_tracking", "auto_face_tracking_yolo"}:
        try:
            values = _face_centers(frames)
        except ImportError:
            values = []
        if any(value is not None for value in values):
            used_mode = "face_tracking"
    if not values or not any(value is not None for value in values):
        values = _motion_centers(frames)
        used_mode = "motion_tracking"
    weight = max(0.0, min(0.99, float(smoothing)))
    smoothed = 0.5
    keyframes: list[dict[str, float]] = []
    for index, value in enumerate(values):
        target = value if value is not None else smoothed
        smoothed = weight * smoothed + (1.0 - weight) * target
        keyframes.append(
            {
                "time_sec": round(index / max(1, fps), 3),
                "focus_x": round(max(0.05, min(0.95, smoothed)), 4),
            }
        )
    return keyframes, used_mode


def track_focus_x(
    source: Path,
    pieces: Sequence[tuple[int, int]],
    sample_rate: int,
    *,
    mode: str = "motion_tracking",
) -> tuple[float, str]:
    frames = frames_from_pieces(source, pieces, sample_rate)
    if mode == "face_tracking":
        try:
            face_focus = _face_focus(frames)
        except ImportError:
            face_focus = None
        if face_focus is not None:
            return face_focus, "face_tracking"
        return focus_x_from_frames(frames), "motion_tracking"
    return focus_x_from_frames(frames), "motion_tracking"


def frames_from_pieces(
    source: Path,
    pieces: Sequence[tuple[int, int]],
    sample_rate: int,
    *,
    width: int = 64,
    height: int = 36,
    fps: int = 2,
) -> np.ndarray:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise IngestError("FFmpeg is not available for motion tracking.")
    chunks: list[bytes] = []
    for start, end in pieces:
        duration = (end - start) / sample_rate
        if duration <= 0:
            continue
        command = [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start / sample_rate:.6f}",
            "-t",
            f"{duration:.6f}",
            "-i",
            str(source),
            "-vf",
            f"fps={fps},scale={width}:{height},format=gray",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "pipe:1",
        ]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise IngestError(f"Motion tracking failed: {exc}") from exc
        if result.returncode != 0:
            continue
        chunks.append(result.stdout)
    if not chunks:
        return np.empty((0, height, width), dtype=np.uint8)
    raw = b"".join(chunks)
    size = width * height
    count = len(raw) // size
    if count == 0:
        return np.empty((0, height, width), dtype=np.uint8)
    return np.frombuffer(raw[: count * size], dtype=np.uint8).reshape(count, height, width)


def _face_focus(frames: np.ndarray) -> float | None:
    if len(frames) == 0:
        return None
    import cv2  # type: ignore[import-not-found]

    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(str(cascade_path))
    centers: list[float] = []
    for frame in frames[:: max(1, len(frames) // 20)]:
        faces = detector.detectMultiScale(frame, scaleFactor=1.1, minNeighbors=4)
        for x, _y, width, _height in faces:
            centers.append((x + width / 2) / frame.shape[1])
    if not centers:
        return None
    return max(0.05, min(0.95, sum(centers) / len(centers)))
