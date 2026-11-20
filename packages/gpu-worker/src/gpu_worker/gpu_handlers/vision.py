"""OpenCV face tracking and blur-audit handlers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gpu_worker.handlers import Handler, HandlerError
from gpu_worker.progress import report

if TYPE_CHECKING:
    from gpu_worker.settings import Settings

def make_vision_blur_handler(settings: Settings) -> Handler:
    """Sample frames and report Laplacian-variance blur scores."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("vision_blur requires a video artifact")
        try:
            import cv2
        except Exception as exc:  # noqa: BLE001 - optional dependency
            raise HandlerError(f"OpenCV is not installed: {exc}") from exc
        capture = cv2.VideoCapture(str(input_paths[0]))
        if not capture.isOpened():
            raise HandlerError(f"cannot open video: {input_paths[0]}")
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
        sample = max(1, round(fps / max(0.2, float(params.get("fps") or 1.0))))
        frames: list[dict[str, Any]] = []
        index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if index % sample:
                    index += 1
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                frames.append(
                    {
                        "frame": index,
                        "time": round(index / fps, 4),
                        "score": round(score, 3),
                        "blurry": score < float(params.get("threshold") or 80.0),
                    }
                )
                index += 1
        finally:
            capture.release()
        payload = {
            "schema_version": 1,
            "fps": round(fps, 3),
            "sampled": len(frames),
            "frames": frames,
        }
        target = work_dir / "blur.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return [target]

    return handler


def make_face_track_handler(settings: Settings) -> Handler:
    """Track the largest face with OpenCV and write normalized keyframes."""

    def handler(
        params: dict[str, Any], input_paths: list[Path], work_dir: Path
    ) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        if not input_paths:
            raise HandlerError("face_track requires an input video artifact")
        try:
            import cv2
        except Exception as exc:  # noqa: BLE001 - optional dependency
            raise HandlerError(f"OpenCV is not installed: {exc}") from exc
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(str(cascade_path))
        if cascade.empty():
            raise HandlerError("OpenCV face cascade is unavailable")
        capture = cv2.VideoCapture(str(input_paths[0]))
        if not capture.isOpened():
            raise HandlerError(f"cannot open video: {input_paths[0]}")
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
        sample = max(1, round(fps / max(1.0, float(params.get("fps") or 5.0))))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        keyframes: list[dict[str, Any]] = []
        index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if index % sample:
                    index += 1
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
                if len(faces):
                    x, y, w, h = max(faces, key=lambda item: int(item[2]) * int(item[3]))
                    keyframes.append(
                        {
                            "frame": index,
                            "time": round(index / fps, 4),
                            "bbox": [
                                round(float(x) / max(1, width), 6),
                                round(float(y) / max(1, height), 6),
                                round(float(w) / max(1, width), 6),
                                round(float(h) / max(1, height), 6),
                            ],
                        }
                    )
                index += 1
                if total_frames and index % 60 == 0:
                    report(
                        "tracking faces",
                        10 + round(80 * min(1.0, index / total_frames)),
                    )
        finally:
            capture.release()
        payload = {
            "schema_version": 1,
            "mode": "opencv_haar",
            "fps": round(fps, 3),
            "width": width,
            "height": height,
            "keyframes": keyframes,
        }
        target = work_dir / "tracking.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return [target]

    return handler
