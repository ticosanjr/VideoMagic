"""CPU-only scene layout and face statistics."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vf_shared.scene_rules import classify_layout as _classify_layout
from vf_shared.scene_rules import median as _median
from vf_shared.scene_rules import sample_times as _rules_sample_times

from videoflow.application.scene_intel.detect import SceneSpan
from videoflow.domain.state import MediaInfo


@dataclass(frozen=True, slots=True)
class SceneVisual:
    face_count: int = 0
    face_cx: float | None = None
    face_cy: float | None = None
    face_w: float | None = None
    face_h: float | None = None
    face_area_ratio: float = 0.0
    edge_density: float = 0.0
    sharpness_laplacian: float = 0.0
    sampled_frames: int = 0


def _sample_times(span: SceneSpan, *, max_frames: int = 3, interval: float = 1.0) -> list[float]:
    return _rules_sample_times(
        span.start_sec,
        span.end_sec,
        max_frames=max_frames,
        interval=interval,
    )


class _FaceBackend:
    def __init__(self) -> None:
        self._mediapipe: Any | None = None
        try:
            import mediapipe as mp  # type: ignore[import-not-found]

            self._mediapipe = mp.solutions.face_detection.FaceDetection(
                model_selection=1,
                min_detection_confidence=0.45,
            )
        except Exception:  # noqa: BLE001 - optional dependency
            self._mediapipe = None
        self._cascade: Any | None = None
        try:
            import cv2

            cascade = cv2.CascadeClassifier(
                str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
            )
            self._cascade = None if cascade.empty() else cascade
        except Exception:  # noqa: BLE001 - optional dependency
            self._cascade = None

    def detect(self, frame: Any, cv2: Any) -> tuple[int, float, float, float, float] | None:
        direct = self._detect_region(frame, cv2)
        if direct is not None:
            return direct
        height, width = frame.shape[:2]
        if height < 40 or width < 40:
            return None
        corner = 0.30
        cw = max(8, int(width * corner))
        ch = max(8, int(height * corner))
        origins = (
            (0, 0),
            (width - cw, 0),
            (0, height - ch),
            (width - cw, height - ch),
        )
        for x0, y0 in origins:
            crop = frame[y0 : y0 + ch, x0 : x0 + cw]
            if crop.size == 0:
                continue
            enlarged = cv2.resize(crop, (cw * 2, ch * 2), interpolation=cv2.INTER_CUBIC)
            found = self._detect_region(enlarged, cv2)
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

    def _detect_region(
        self, frame: Any, cv2: Any
    ) -> tuple[int, float, float, float, float] | None:
        if self._mediapipe is not None:
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = self._mediapipe.process(rgb)
                if result.detections:
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
            except Exception:  # noqa: BLE001 - fall back to Haar
                pass
        if self._cascade is None:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
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


def analyze_visuals(
    proxy: Path,
    spans: list[SceneSpan],
    media: MediaInfo,
    *,
    source_topology: str = "auto",
    max_frames_per_scene: int = 3,
) -> tuple[list[SceneVisual], list[str]]:
    warnings: list[str] = []
    try:
        import cv2
    except Exception as exc:  # noqa: BLE001 - optional dependency
        warnings.append(f"OpenCV unavailable; layout falls back to footage: {exc}")
        return [SceneVisual() for _ in spans], warnings
    try:
        probe = cv2.VideoCapture(str(proxy))
    except Exception as exc:  # noqa: BLE001 - optional dependency
        warnings.append(f"Cannot open scene proxy: {exc}")
        return [SceneVisual() for _ in spans], warnings
    if not probe.isOpened():
        probe.release()
        warnings.append("Cannot open scene proxy")
        return [SceneVisual() for _ in spans], warnings
    probe.release()
    topology = source_topology
    if topology == "auto":
        ratio = media.width / max(1, media.height)
        topology = "dual_canvas" if abs(ratio - 3.55) < 0.15 else "single_16x9"
    fps = media.fps_num / max(1, media.fps_den)
    import threading
    from concurrent.futures import ThreadPoolExecutor

    local = threading.local()

    def backend_for() -> _FaceBackend:
        instance = getattr(local, "backend", None)
        if instance is None:
            instance = _FaceBackend()
            local.backend = instance
        return instance

    def one(span: SceneSpan) -> SceneVisual:
        capture = cv2.VideoCapture(str(proxy))
        if not capture.isOpened():
            capture.release()
            return SceneVisual()
        faces: list[tuple[int, float, float, float, float]] = []
        edges: list[float] = []
        sharp: list[float] = []
        samples = _sample_times(
            span, max_frames=max_frames_per_scene, interval=2.0
        )
        capture.set(cv2.CAP_PROP_POS_MSEC, span.start_sec * 1000.0)
        cursor = span.start_sec
        try:
            for timestamp in samples:
                skip = max(0, round((timestamp - cursor) * fps))
                for _ in range(skip):
                    if not capture.grab():
                        break
                ok, frame = capture.read()
                cursor = timestamp
                if not ok:
                    capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
                    ok, frame = capture.read()
                if not ok:
                    continue
                if topology == "dual_canvas":
                    half = frame.shape[1] // 2
                    cam, screen = frame[:, half:], frame[:, :half]
                else:
                    cam = screen = frame
                detected = backend_for().detect(cam, cv2)
                if detected is not None:
                    faces.append(detected)
                gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                edges.append(float(cv2.Canny(gray, 80, 180).mean()) / 255.0)
                crop = gray
                if detected is not None:
                    _count, cx, cy, fw, fh = detected
                    height, width = gray.shape[:2]
                    x0 = max(0, int((cx - fw / 2) * width))
                    x1 = min(width, int((cx + fw / 2) * width))
                    y0 = max(0, int((cy - fh / 2) * height))
                    y1 = min(height, int((cy + fh / 2) * height))
                    if x1 > x0 and y1 > y0:
                        crop = gray[y0:y1, x0:x1]
                sharp.append(float(cv2.Laplacian(crop, cv2.CV_64F).var()))
        finally:
            capture.release()
        if faces:
            count = max(item[0] for item in faces)
            cx = _median([item[1] for item in faces])
            cy = _median([item[2] for item in faces])
            fw = _median([item[3] for item in faces])
            fh = _median([item[4] for item in faces])
            area = fw * fh
        else:
            count = 0
            cx = cy = fw = fh = area = 0.0
        return SceneVisual(
            face_count=count,
            face_cx=cx if count else None,
            face_cy=cy if count else None,
            face_w=fw if count else None,
            face_h=fh if count else None,
            face_area_ratio=round(area, 6),
            edge_density=_median(edges),
            sharpness_laplacian=_median(sharp),
            sampled_frames=len(edges),
        )

    workers = min(16, max(1, os.cpu_count() or 4), max(1, len(spans)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, spans))
    return results, warnings


def classify_layout(visual: SceneVisual, media: MediaInfo, topology: str) -> str:
    return _classify_layout(
        face_count=visual.face_count,
        face_area_ratio=visual.face_area_ratio,
        edge_density=visual.edge_density,
        width=media.width,
        height=media.height,
        topology=topology,
    )
