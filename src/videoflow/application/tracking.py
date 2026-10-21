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
