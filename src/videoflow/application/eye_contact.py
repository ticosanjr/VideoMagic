"""Pure eye-contact analyzers for the decoupage step.

Keeping the MediaPipe, YOLO, and OpenCV heuristics out of the step makes the
orchestration easier to test and lets optional backends fail independently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def cascades(cv2: Any) -> tuple[Any, Any] | None:
    try:
        base = Path(cv2.data.haarcascades)
        face = cv2.CascadeClassifier(str(base / "haarcascade_frontalface_default.xml"))
        eye = cv2.CascadeClassifier(str(base / "haarcascade_eye.xml"))
        if face.empty() or eye.empty():
            return None
        return face, eye
    except Exception:  # noqa: BLE001 - broken optional install
        return None


def analyze_frame(
    cv2: Any,
    image: Any,
    face_cascade: Any,
    eye_cascade: Any,
    *,
    min_face_ratio: float,
    center_tolerance: float,
    min_eyes: int,
) -> tuple[bool, float, float]:
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    if len(faces) == 0:
        return False, 0.0, 0.0
    x, y, w, h = max(faces, key=lambda item: int(item[2]) * int(item[3]))
    face_ratio = float(w) / max(1, width)
    center_x = (x + w / 2) / max(1, width)
    offset = abs(center_x - 0.5)
    roi = gray[y : y + h, x : x + w]
    eyes = eye_cascade.detectMultiScale(roi, scaleFactor=1.1, minNeighbors=4)
    eye_count = len(eyes)
    confidence = min(
        1.0,
        0.55 * min(1.0, face_ratio / max(0.01, min_face_ratio))
        + 0.25 * (1.0 - min(1.0, offset / max(0.01, center_tolerance)))
        + 0.20 * min(1.0, eye_count / max(1, min_eyes)),
    )
    eye_contact = (
        face_ratio >= min_face_ratio
        and offset <= center_tolerance
        and eye_count >= min_eyes
    )
    return eye_contact, confidence, face_ratio


def analyze_mediapipe(
    face_mesh: Any,
    cv2: Any,
    image: Any,
    *,
    min_face_ratio: float,
    center_tolerance: float,
    min_eyes: int,
) -> tuple[bool, float, float]:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    result = face_mesh.process(rgb)
    faces = getattr(result, "multi_face_landmarks", None) or []
    if not faces:
        return False, 0.0, 0.0
    landmarks = faces[0].landmark
    xs = [float(item.x) for item in landmarks]
    face_ratio = max(0.0, max(xs) - min(xs))
    center = (min(xs) + max(xs)) / 2.0
    offset = abs(center - 0.5)

    def eye_open(upper: int, lower: int, left: int, right: int) -> float:
        horizontal = abs(float(landmarks[right].x) - float(landmarks[left].x))
        vertical = abs(float(landmarks[lower].y) - float(landmarks[upper].y))
        return vertical / max(1e-6, horizontal)

    eyes = sum(
        1
        for value in (
            eye_open(159, 145, 33, 133),
            eye_open(386, 374, 362, 263),
        )
        if value > 0.10
    )
    required_eyes = max(0, min(2, min_eyes))
    eye_contact = (
        face_ratio >= min_face_ratio
        and offset <= center_tolerance
        and eyes >= required_eyes
    )
    confidence = min(
        1.0,
        0.55 * min(1.0, face_ratio / max(0.01, min_face_ratio))
        + 0.25 * (1.0 - min(1.0, offset / max(0.01, center_tolerance)))
        + 0.20 * min(1.0, eyes / max(1, required_eyes)),
    )
    return eye_contact, confidence, face_ratio


def analyze_yolo(
    model: Any,
    image: Any,
    *,
    min_face_ratio: float,
    center_tolerance: float,
    confidence: float = 0.35,
) -> tuple[bool, float, float]:
    results = model.predict(image, conf=confidence, verbose=False)
    boxes = getattr(results[0], "boxes", None) if results else None
    raw = getattr(boxes, "xyxy", None) if boxes is not None else None
    rows = raw.tolist() if hasattr(raw, "tolist") else list(raw or [])
    width = float(image.shape[1])
    best: tuple[float, float, float] | None = None
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 4:
            continue
        x1, y1, x2, y2 = (float(value) for value in row[:4])
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        face_ratio = max(0.0, x2 - x1) / max(1.0, width)
        center = (x1 + x2) / 2.0 / max(1.0, width)
        offset = abs(center - 0.5)
        if best is None or area > best[2]:
            best = (face_ratio, offset, area)
    if best is None:
        return False, 0.0, 0.0
    face_ratio, offset, _area = best
    eye_contact = face_ratio >= min_face_ratio and offset <= center_tolerance
    score = min(
        1.0,
        0.65 * min(1.0, face_ratio / max(0.01, min_face_ratio))
        + 0.35 * (1.0 - min(1.0, offset / max(0.01, center_tolerance))),
    )
    return eye_contact, score, face_ratio


def merge_intervals(
    frames: list[tuple[int, float]], *, fps: float, max_gap: float = 1.25
) -> list[dict[str, float]]:
    intervals: list[dict[str, float]] = []
    for index, confidence_value in frames:
        timestamp = index / fps
        if intervals and timestamp - intervals[-1]["end_sec"] <= max_gap / fps:
            intervals[-1]["end_sec"] = timestamp
            intervals[-1]["confidence"] = max(
                intervals[-1]["confidence"], confidence_value
            )
        else:
            intervals.append(
                {
                    "start_sec": timestamp,
                    "end_sec": timestamp,
                    "confidence": confidence_value,
                }
            )
    for interval in intervals:
        interval["start_sec"] = round(interval["start_sec"], 3)
        interval["end_sec"] = round(interval["end_sec"], 3)
        interval["confidence"] = round(interval["confidence"], 3)
    return intervals
