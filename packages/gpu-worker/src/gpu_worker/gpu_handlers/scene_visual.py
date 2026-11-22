"""Face detection, visual statistics and scene classification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vf_shared.scene_rules import median as _rules_median
from vf_shared.scene_rules import sample_times as _rules_sample_times

from gpu_worker.handler_types import HandlerError


def _scene_median(values: list[float], default: float = 0.0) -> float:
    return _rules_median(values, default)

def _scene_sample_times(
    start: float,
    end: float,
    *,
    max_frames: int = 3,
    interval: float = 1.5,
) -> list[float]:
    return _rules_sample_times(
        start,
        end,
        max_frames=max_frames,
        interval=interval,
    )


def _scene_face_backend(cv2: Any) -> Any:
    try:
        import mediapipe as mp  # type: ignore[import-not-found]

        detector = mp.solutions.face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=0.45,
        )

        def region(frame: Any) -> tuple[int, float, float, float, float] | None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = detector.process(rgb)
            if not result.detections:
                return None
            detection = max(
                result.detections,
                key=lambda item: item.location_data.relative_bounding_box.width
                * item.location_data.relative_bounding_box.height,
            )
            box = detection.location_data.relative_bounding_box
            return (
                1,
                float(box.xmin + box.width / 2),
                float(box.ymin + box.height / 2),
                float(box.width),
                float(box.height),
            )

        def detect(frame: Any) -> tuple[int, float, float, float, float] | None:
            direct = region(frame)
            if direct is not None:
                return direct
            height, width = frame.shape[:2]
            corner = 0.30
            cw = max(8, int(width * corner))
            ch = max(8, int(height * corner))
            for x0, y0 in (
                (0, 0),
                (width - cw, 0),
                (0, height - ch),
                (width - cw, height - ch),
            ):
                crop = frame[y0 : y0 + ch, x0 : x0 + cw]
                if crop.size == 0:
                    continue
                enlarged = cv2.resize(
                    crop, (cw * 2, ch * 2), interpolation=cv2.INTER_CUBIC
                )
                found = region(enlarged)
                if found is None:
                    continue
                count, cx, cy, fw, fh = found
                return (
                    count,
                    (x0 + cx * cw) / max(1, width),
                    (y0 + cy * ch) / max(1, height),
                    fw * cw / max(1, width),
                    fh * ch / max(1, height),
                )
            return None

        return detect
    except Exception:  # noqa: BLE001 - Haar fallback
        try:
            cascade = cv2.CascadeClassifier(
                str(
                    Path(cv2.data.haarcascades)
                    / "haarcascade_frontalface_default.xml"
                )
            )
        except Exception:  # noqa: BLE001 - OpenCV build without Haar support
            return lambda frame: None
        if cascade.empty():
            return lambda frame: None

        def detect_haar(frame: Any) -> tuple[int, float, float, float, float] | None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
            if not len(faces):
                return None
            height, width = gray.shape[:2]
            x, y, w, h = max(faces, key=lambda item: int(item[2]) * int(item[3]))
            return (
                len(faces),
                (float(x) + float(w) / 2) / max(1, width),
                (float(y) + float(h) / 2) / max(1, height),
                float(w) / max(1, width),
                float(h) / max(1, height),
            )

        return detect_haar

def _scene_visuals(
    proxy: Path,
    spans: list[tuple[float, float]],
    *,
    topology: str,
    max_frames: int = 3,
) -> list[dict[str, Any]]:
    """Sample every scene with one sequential decode pass.

    Random ``CAP_PROP_POS_MSEC`` seeks force the decoder to restart at each
    keyframe, which dominated the full scene pipeline. Walking the 10 fps proxy
    once and analyzing only the selected frames keeps the same measurements
    while removing the seek cost.
    """

    import cv2

    capture = cv2.VideoCapture(str(proxy))
    if not capture.isOpened():
        raise HandlerError(f"cannot open scene proxy: {proxy}")
    detect = _scene_face_backend(cv2)
    faces: list[list[tuple[int, float, float, float, float]]] = [[] for _ in spans]
    edges: list[list[float]] = [[] for _ in spans]
    sharp: list[list[float]] = [[] for _ in spans]
    targets: list[tuple[float, int]] = []
    for index, (start, end) in enumerate(spans):
        for timestamp in _scene_sample_times(start, end, max_frames=max_frames):
            targets.append((timestamp, index))
    targets.sort()

    def measure(frame: Any, index: int) -> None:
        if topology == "dual_canvas":
            half = frame.shape[1] // 2
            cam, screen = frame[:, half:], frame[:, :half]
        else:
            cam = screen = frame
        face = detect(cam)
        if face is not None:
            faces[index].append(face)
        gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        edges[index].append(float(cv2.Canny(gray, 80, 180).mean()) / 255.0)
        crop = gray
        if face is not None:
            _count, cx, cy, fw, fh = face
            height, width = gray.shape[:2]
            x0 = max(0, int((cx - fw / 2) * width))
            x1 = min(width, int((cx + fw / 2) * width))
            y0 = max(0, int((cy - fh / 2) * height))
            y1 = min(height, int((cy + fh / 2) * height))
            if x1 > x0 and y1 > y0:
                crop = gray[y0:y1, x0:x1]
        sharp[index].append(float(cv2.Laplacian(crop, cv2.CV_64F).var()))

    cursor = 0
    try:
        while cursor < len(targets):
            ok, frame = capture.read()
            if not ok:
                break
            position = float(capture.get(cv2.CAP_PROP_POS_MSEC) or 0.0) / 1000.0
            while cursor < len(targets) and targets[cursor][0] <= position + 0.05:
                measure(frame, targets[cursor][1])
                cursor += 1
    finally:
        capture.release()

    results: list[dict[str, Any]] = []
    for index in range(len(spans)):
        scene_faces = faces[index]
        if scene_faces:
            count = max(item[0] for item in scene_faces)
            cx = _scene_median([item[1] for item in scene_faces])
            cy = _scene_median([item[2] for item in scene_faces])
            fw = _scene_median([item[3] for item in scene_faces])
            fh = _scene_median([item[4] for item in scene_faces])
            area = fw * fh
        else:
            count = 0
            cx = cy = fw = fh = area = 0.0
        results.append(
            {
                "face_count": count,
                "face_cx": cx if count else None,
                "face_cy": cy if count else None,
                "face_w": fw if count else None,
                "face_h": fh if count else None,
                "face_area_ratio": round(area, 6),
                "edge_density": _scene_median(edges[index]),
                "sharpness_laplacian": _scene_median(sharp[index]),
            }
        )
    return results
