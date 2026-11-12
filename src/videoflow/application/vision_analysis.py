"""Optional OCR, subject masks, and point tracking for footage recipes."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from videoflow.runtime import find_binary


def extract_frames(
    video: Path,
    directory: Path,
    *,
    fps: float = 1.0,
    max_frames: int = 120,
    width: int = 1280,
) -> list[Path]:
    binary = find_binary("ffmpeg")
    if binary is None:
        raise RuntimeError("FFmpeg is not available.")
    directory = Path(directory)
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    command = [
        binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video),
        "-vf",
        f"fps={max(0.01, fps)},scale={max(16, width)}:-2",
        "-frames:v",
        str(max(1, max_frames)),
        str(directory / "frame-%05d.png"),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "Could not extract vision frames: "
            + (completed.stderr.strip() or f"exit {completed.returncode}")
        )
    return sorted(directory.glob("frame-*.png"))


def ocr_boxes(
    image_path: Path, *, language: str = "por+eng", min_confidence: float = 0.35
) -> list[dict[str, Any]]:
    """Return text boxes when pytesseract and the tesseract binary exist."""

    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return []
    try:
        with Image.open(image_path) as image:
            data = pytesseract.image_to_data(
                image,
                lang=language,
                output_type=pytesseract.Output.DICT,
            )
    except Exception:
        return []
    boxes: list[dict[str, Any]] = []
    for index, text in enumerate(data.get("text", [])):
        value = str(text or "").strip()
        try:
            confidence = float(data["conf"][index]) / 100.0
        except (KeyError, IndexError, TypeError, ValueError):
            confidence = 0.0
        if not value or confidence < min_confidence:
            continue
        boxes.append(
            {
                "text": value,
                "confidence": round(confidence, 3),
                "x": int(data["left"][index]),
                "y": int(data["top"][index]),
                "width": int(data["width"][index]),
                "height": int(data["height"][index]),
            }
        )
    return boxes


def segmentation_mask(
    image_path: Path,
    target: Path,
    *,
    backend: str = "auto",
) -> tuple[Path | None, str]:
    """Write a foreground mask PNG. Returns (path, backend_used)."""

    try:
        import cv2
        import numpy as np
    except Exception:
        return None, "none"
    image = cv2.imread(str(image_path))
    if image is None:
        return None, "none"
    height, width = image.shape[:2]
    mask: Any = None
    used = "none"
    if backend in {"auto", "mediapipe"}:
        try:
            import mediapipe as mp

            with mp.solutions.selfie_segmentation.SelfieSegmentation(
                model_selection=1
            ) as segmenter:
                result = segmenter.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            if result.segmentation_mask is not None:
                mask = (result.segmentation_mask > 0.5).astype(np.uint8) * 255
                used = "mediapipe"
        except Exception:
            mask = None
    if mask is None and backend in {"auto", "grabcut"}:
        try:
            rect = (
                int(width * 0.12),
                int(height * 0.08),
                max(1, int(width * 0.76)),
                max(1, int(height * 0.84)),
            )
            grab = np.zeros(image.shape[:2], dtype=np.uint8)
            bgd = np.zeros((1, 65), dtype=np.float64)
            fgd = np.zeros((1, 65), dtype=np.float64)
            cv2.grabCut(
                image,
                grab,
                rect,
                bgd,
                fgd,
                3,
                cv2.GC_INIT_WITH_RECT,
            )
            mask = np.where(
                (grab == cv2.GC_FGD) | (grab == cv2.GC_PR_FGD), 255, 0
            ).astype(np.uint8)
            used = "grabcut"
        except Exception:
            mask = None
    if mask is None:
        return None, "none"
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target), mask)
    return target, used


def track_box(
    video: Path,
    box: tuple[int, int, int, int],
    *,
    start_sec: float = 0.0,
    end_sec: float = 0.0,
    fps: float = 2.0,
    max_points: int = 80,
) -> list[dict[str, float]]:
    """Track feature points inside a box with pyramidal Lucas-Kanade."""

    try:
        import cv2
        import numpy as np
    except Exception:
        return []
    binary = find_binary("ffmpeg")
    if binary is None:
        return []
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return []
    try:
        source_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start_sec) * 1000)
        ok, frame = cap.read()
        if not ok or frame is None:
            return []
        x, y, width, height = box
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        mask[max(0, y) : y + max(1, height), max(0, x) : x + max(1, width)] = 255
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        points = cv2.goodFeaturesToTrack(
            gray, maxCorners=max_points, qualityLevel=0.01, minDistance=7, mask=mask
        )
        if points is None:
            return []
        frames: list[dict[str, float]] = []
        step = max(1, int(round(max(1.0, source_fps) / max(0.1, fps))))
        index = 0
        while True:
            timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if end_sec > 0 and timestamp > end_sec:
                break
            frames.append(
                {
                    "time": round(timestamp, 3),
                    "x": round(float(np.mean(points[:, 0, 0])), 2),
                    "y": round(float(np.mean(points[:, 0, 1])), 2),
                }
            )
            for _ in range(step):
                ok, frame = cap.read()
                if not ok or frame is None:
                    return frames
            next_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            moved, status, _error = cv2.calcOpticalFlowPyrLK(
                gray, next_gray, points, None
            )
            if moved is None or status is None:
                break
            good = status.reshape(-1) == 1
            if not bool(np.any(good)):
                break
            points = moved[good].reshape(-1, 1, 2)
            gray = next_gray
            index += 1
            if index > 1000:
                break
        return frames
    finally:
        cap.release()
