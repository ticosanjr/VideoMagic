"""Lightweight Short reframing focus estimation.

Motion tracking uses FFmpeg-decoded low-resolution frames and NumPy. Face
tracking is optional and only activates when OpenCV is installed.
"""

from __future__ import annotations

import statistics
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from videoflow.application.vision_backends import (
    mediapipe_model_path,
    mediapipe_model_selection,
    resolve_tracking_backend,
    yolo_model_path,
)
from videoflow.domain.errors import IngestError
from videoflow.runtime import find_binary


def focus_x_from_frames(frames: np.ndarray) -> float:
    if frames.ndim == 4:
        frames = frames.astype(np.float32).mean(axis=-1)
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
        x, _y, width, _height = max(faces, key=lambda item: int(item[2]) * int(item[3]))
        centers.append((x + width / 2) / max(1, frame.shape[1]))
    return centers


def _face_centers_mediapipe_legacy(
    frames: np.ndarray, *, model_selection: int = 1
) -> list[float | None]:
    import mediapipe as mp  # type: ignore[import-not-found]

    detector = mp.solutions.face_detection.FaceDetection(
        model_selection=mediapipe_model_selection(model_selection),
        min_detection_confidence=0.4,
    )
    centers: list[float | None] = []
    try:
        for frame in frames:
            rgb = frame if frame.ndim == 3 else np.stack([frame] * 3, axis=-1)
            result = detector.process(rgb)
            detections = result.detections or []
            if not detections:
                centers.append(None)
                continue
            best = max(
                detections,
                key=lambda item: (
                    float(item.location_data.relative_bounding_box.width)
                    * float(item.location_data.relative_bounding_box.height)
                ),
            )
            box = best.location_data.relative_bounding_box
            centers.append(float(box.xmin + box.width / 2))
    finally:
        detector.close()
    return centers


def _face_centers_mediapipe(
    frames: np.ndarray,
    *,
    model_selection: int = 1,
    model_path: str = "",
) -> list[float | None]:
    import mediapipe as mp  # type: ignore[import-not-found]

    if getattr(mp, "solutions", None) is not None:
        return _face_centers_mediapipe_legacy(frames, model_selection=model_selection)

    resolved = mediapipe_model_path(model_path)
    if not resolved:
        raise ImportError(
            "MediaPipe Tasks needs a local face model (set VIDEOWFLOW_MEDIAPIPE_MODEL)"
        )
    from mediapipe.tasks import python as mp_python  # type: ignore[import-not-found]
    from mediapipe.tasks.python import vision as mp_vision  # type: ignore[import-not-found]

    base = mp_python.BaseOptions(model_asset_path=resolved)
    options = mp_vision.FaceDetectorOptions(
        base_options=base,
        min_detection_confidence=0.4,
    )
    centers: list[float | None] = []
    with mp_vision.FaceDetector.create_from_options(options) as detector:
        for frame in frames:
            rgb = frame if frame.ndim == 3 else np.stack([frame] * 3, axis=-1)
            image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=np.ascontiguousarray(rgb),
            )
            result = detector.detect(image)
            detections = result.detections or []
            if not detections:
                centers.append(None)
                continue
            best = max(
                detections,
                key=lambda item: int(item.bounding_box.width) * int(item.bounding_box.height),
            )
            box = best.bounding_box
            frame_width = max(1, int(rgb.shape[1]))
            centers.append(float(box.origin_x + box.width / 2) / frame_width)
    return centers


@lru_cache(maxsize=2)
def _load_yolo_model(path: str) -> object:
    """Load a YOLO model once per resolved path.

    Shorts reframing calls the tracker once per clip; loading the model for
    every clip would dominate the runtime.
    """

    from ultralytics import YOLO  # type: ignore[import-not-found]

    return YOLO(path)


def _face_centers_yolo(
    frames: np.ndarray, *, model_path: str = "", confidence: float = 0.35
) -> list[float | None]:
    resolved = yolo_model_path(model_path)
    if not resolved:
        raise ImportError("Set VIDEOWFLOW_YOLO_MODEL to a local YOLO model file.")
    model = _load_yolo_model(resolved)
    centers: list[float | None] = []
    for frame in frames:
        rgb = frame if frame.ndim == 3 else np.stack([frame] * 3, axis=-1)
        results = model.predict(rgb[:, :, ::-1], conf=confidence, verbose=False)
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
    if frames.ndim == 4:
        # Face backends sample color frames; motion needs one channel.
        frames = frames.astype(np.float32).mean(axis=-1).astype(np.uint8)
    values = frames.astype(np.int16)
    difference = np.abs(np.diff(values, axis=0))
    mask = difference > 18
    weights = mask.sum(axis=1, dtype=np.float64)
    totals = weights.sum(axis=1)
    x = np.arange(weights.shape[1], dtype=np.float64)
    centroids = np.zeros_like(totals)
    np.divide(weights @ x, totals, out=centroids, where=totals > 0)
    scale = max(1, weights.shape[1] - 1)
    return [None] + [
        None if total <= 0 else float(centroid) / scale
        for centroid, total in zip(centroids, totals, strict=True)
    ]


@dataclass(frozen=True, slots=True)
class TrackingResult:
    keyframes: list[dict[str, float]]
    backend: str
    requested: str
    reason: str
    frames: int
    detections: int


def _fill_gaps(values: list[float | None]) -> list[float]:
    """Fill missing focus samples in one forward and one interpolation pass."""

    valid = [index for index, value in enumerate(values) if value is not None]
    if not valid:
        return [0.5 for _ in values]
    filled = [0.5 if value is None else float(value) for value in values]
    first, last = valid[0], valid[-1]
    for index in range(first):
        filled[index] = filled[first]
    for index in range(last + 1, len(filled)):
        filled[index] = filled[last]
    previous = first
    for index in valid[1:]:
        span = index - previous
        if span > 1:
            start, end = filled[previous], filled[index]
            for offset in range(1, span):
                filled[previous + offset] = start + (end - start) * offset / span
        previous = index
    return filled


def track_focus(
    source: Path,
    pieces: Sequence[tuple[int, int]],
    sample_rate: int,
    *,
    mode: str = "motion_tracking",
    smoothing: float = 0.85,
    fps: int = 2,
    backend: str = "",
    yolo_model: str = "",
    yolo_confidence: float = 0.35,
    mediapipe_model: int = 1,
    mediapipe_model_path: str = "",
) -> TrackingResult:
    """Return focus keyframes plus the concrete backend and fallback reason."""

    requested = backend or "auto"
    resolved, reason = resolve_tracking_backend(
        requested,
        mode,
        yolo_model=yolo_model,
        mediapipe_model_path=mediapipe_model_path,
    )
    # Haar needs more than 64x36 to find a face; only the neural backends
    # additionally need colour.
    wide = resolved in {"mediapipe", "yolo", "opencv_haar"}
    color = resolved in {"mediapipe", "yolo"}
    frames = frames_from_pieces(
        source,
        pieces,
        sample_rate,
        fps=fps,
        width=256 if wide else 64,
        height=144 if wide else 36,
        color=color,
    )
    if len(frames) == 0:
        return TrackingResult(
            [{"time_sec": 0.0, "focus_x": 0.5}],
            "motion_tracking",
            requested,
            "no frames decoded",
            0,
            0,
        )

    values: list[float | None] = []
    used = "motion_tracking"
    if resolved == "mediapipe":
        try:
            values = _face_centers_mediapipe(
                frames,
                model_selection=mediapipe_model,
                model_path=mediapipe_model_path,
            )
            used = "mediapipe"
        except Exception as exc:  # noqa: BLE001 - optional dependency
            reason = f"mediapipe failed: {exc}"
    elif resolved == "yolo":
        try:
            values = _face_centers_yolo(frames, model_path=yolo_model, confidence=yolo_confidence)
            used = "yolo"
        except Exception as exc:  # noqa: BLE001 - optional dependency/model
            reason = f"yolo failed: {exc}"
    elif resolved == "opencv_haar":
        try:
            values = _face_centers(frames)
            used = "opencv_haar"
        except Exception as exc:  # noqa: BLE001 - optional dependency
            reason = f"opencv failed: {exc}"

    detections = sum(1 for value in values if value is not None)
    if not values or detections == 0:
        values = _motion_centers(frames)
        used = "motion_tracking"
        if resolved != "motion_tracking":
            reason = (
                f"no face detections ({reason}); used motion"
                if reason
                else "no face detections; used motion"
            )
        detections = sum(1 for value in values if value is not None)

    filled = _fill_gaps(values)
    weight = max(0.0, min(0.99, float(smoothing)))
    smoothed = filled[0] if filled else 0.5
    keyframes: list[dict[str, float]] = []
    for index, value in enumerate(filled):
        smoothed = weight * smoothed + (1.0 - weight) * value
        keyframes.append(
            {
                "time_sec": round(index / max(1, fps), 3),
                "focus_x": round(max(0.05, min(0.95, smoothed)), 4),
            }
        )
    return TrackingResult(
        keyframes,
        used,
        requested,
        reason,
        len(frames),
        detections,
    )


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
    """Backward-compatible wrapper used by existing callers and tests."""

    result = track_focus(
        source,
        pieces,
        sample_rate,
        mode=mode,
        smoothing=smoothing,
        fps=fps,
        backend=backend,
    )
    legacy = (
        "face_tracking"
        if result.backend in {"opencv_haar", "mediapipe", "yolo"}
        else "motion_tracking"
    )
    return result.keyframes, legacy


def track_focus_x_report(
    source: Path,
    pieces: Sequence[tuple[int, int]],
    sample_rate: int,
    *,
    mode: str = "motion_tracking",
    backend: str = "",
    yolo_model: str = "",
    yolo_confidence: float = 0.35,
    mediapipe_model: int = 1,
) -> tuple[float, TrackingResult]:
    result = track_focus(
        source,
        pieces,
        sample_rate,
        mode=mode,
        smoothing=0.85,
        fps=2,
        backend=backend,
        yolo_model=yolo_model,
        yolo_confidence=yolo_confidence,
        mediapipe_model=mediapipe_model,
    )
    focus = (
        float(statistics.median(item["focus_x"] for item in result.keyframes))
        if result.keyframes
        else 0.5
    )
    return focus, result


def track_focus_x(
    source: Path,
    pieces: Sequence[tuple[int, int]],
    sample_rate: int,
    *,
    mode: str = "motion_tracking",
    backend: str = "",
) -> tuple[float, str]:
    focus, result = track_focus_x_report(source, pieces, sample_rate, mode=mode, backend=backend)
    legacy = (
        "face_tracking"
        if result.backend in {"opencv_haar", "mediapipe", "yolo"}
        else "motion_tracking"
    )
    return focus, legacy


def frames_from_pieces(
    source: Path,
    pieces: Sequence[tuple[int, int]],
    sample_rate: int,
    *,
    width: int = 64,
    height: int = 36,
    fps: int = 2,
    color: bool = False,
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
            f"fps={fps},scale={width}:{height},format={'rgb24' if color else 'gray'}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24" if color else "gray",
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
    size = width * height * (3 if color else 1)
    count = len(raw) // size
    shape = (0, height, width, 3) if color else (0, height, width)
    if count == 0:
        return np.empty(shape, dtype=np.uint8)
    reshaped = np.frombuffer(raw[: count * size], dtype=np.uint8)
    return reshaped.reshape((count, height, width, 3) if color else (count, height, width))


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
