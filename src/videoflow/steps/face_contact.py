"""Eye-contact labeling for the decoupage audit.

OpenCV is optional. When it is installed the step samples frames, detects the
largest face and its eyes, and writes green-label spans plus timeline markers.
Without OpenCV the step writes an explicit plan and lets the HILT decoupage
audit handle the manual path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.eye_contact import analyze_frame as _analyze_frame
from videoflow.application.eye_contact import analyze_mediapipe as _analyze_mediapipe
from videoflow.application.eye_contact import analyze_yolo as _analyze_yolo
from videoflow.application.eye_contact import cascades as _cascades
from videoflow.application.eye_contact import merge_intervals as _merge_intervals
from videoflow.application.timeline_meta import add_marker
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import adapter_for, digest_payload
from videoflow.steps.registry import register_step


class FaceContactParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_fps: float = Field(default=1.0, gt=0.0, le=10.0)
    max_frames: int = Field(default=2000, ge=1, le=20000)
    width: int = Field(default=640, ge=64, le=1920)
    min_face_ratio: float = Field(default=0.08, ge=0.005, le=1.0)
    center_tolerance: float = Field(default=0.30, ge=0.0, le=1.0)
    min_eyes: int = Field(default=1, ge=0, le=2)
    backend: Literal["auto", "mediapipe", "yolo", "opencv", "none"] = "auto"
    yolo_model: str = Field(default="", max_length=4000)
    yolo_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    write_markers: bool = True


def _cv2() -> Any | None:
    try:
        import cv2  # type: ignore[import-not-found]

        return cv2
    except Exception:  # noqa: BLE001 - optional dependency
        return None


def _yolo() -> Any | None:
    try:
        from ultralytics import YOLO  # type: ignore[import-not-found]

        return YOLO
    except Exception:  # noqa: BLE001 - optional dependency
        return None


def _mediapipe() -> Any | None:
    try:
        import mediapipe  # type: ignore[import-not-found]

        # Eye contact uses the Face Mesh Solutions API. Recent MediaPipe
        # wheels are Tasks-only; treat those as unavailable and fall back.
        if getattr(mediapipe, "solutions", None) is None:
            return None
        return mediapipe
    except Exception:  # noqa: BLE001 - optional dependency
        return None


@register_step
class FaceContactStep(BaseStep):
    type = "vision.face_contact"
    title = "Eye-contact labels"
    description = (
        "Sample the source, detect direct-to-camera eye contact with MediaPipe, "
        "YOLO, or OpenCV, and write green label spans and timeline markers. The "
        "HILT audit remains the fallback."
    )
    status = "partial"
    icon = "◉"
    color = "#22c55e"
    requires = ("ingest",)
    produces = ("eye_contact",)
    params_model = FaceContactParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = FaceContactParams.model_validate(params)
        target = context.output / "vision" / "face-contact.json"
        backend = options.backend
        cv2 = _cv2() if backend != "none" else None
        mediapipe = _mediapipe() if backend in {"auto", "mediapipe"} else None
        yolo = _yolo() if options.yolo_model and backend in {"auto", "yolo"} else None
        if (
            backend == "none"
            or cv2 is None
            or (backend == "mediapipe" and mediapipe is None)
            or (backend == "yolo" and (yolo is None or not options.yolo_model))
        ):
            reason = (
                "MediaPipe Face Mesh (Solutions API) is not installed. Recent "
                "MediaPipe wheels are Tasks-only; install a legacy vision build "
                "or review the decoupage manually at the HILT gate."
                if backend == "mediapipe"
                else "YOLO requires ultralytics and a local face model path."
                if backend == "yolo"
                else "OpenCV is not installed. Use pip install 'videoflow[vision]' "
                "or review the decoupage manually at the HILT gate."
            )
            payload = {
                "available": False,
                "backend": "mediapipe"
                if backend == "mediapipe"
                else "yolo"
                if backend == "yolo"
                else "none",
                "reason": reason,
                "eye_contact_intervals": [],
                "green_label_count": 0,
            }
            self._write(target, payload)
            context.metadata["eye_contact"] = payload
            context.artifacts["eye_contact"] = str(target)
            context.warnings.append(f"Eye-contact detection skipped: {reason}")
            io.report(100, "Eye-contact analysis unavailable (optional vision extra)")
            return
        use_mediapipe = backend in {"auto", "mediapipe"} and mediapipe is not None
        use_yolo = (
            (backend == "yolo" or (backend == "auto" and not use_mediapipe))
            and yolo is not None
            and bool(options.yolo_model)
        )
        yolo_model_obj = None
        if use_yolo:
            try:
                yolo_model_obj = yolo(options.yolo_model)
            except Exception as exc:  # noqa: BLE001 - optional backend
                if backend == "yolo":
                    payload = {
                        "available": False,
                        "backend": "yolo",
                        "reason": f"YOLO model could not be loaded: {exc}",
                        "eye_contact_intervals": [],
                        "green_label_count": 0,
                    }
                    self._write(target, payload)
                    context.metadata["eye_contact"] = payload
                    context.artifacts["eye_contact"] = str(target)
                    context.warnings.append(f"Eye-contact detection skipped: {payload['reason']}")
                    io.report(100, "Eye-contact analysis unavailable (YOLO load)")
                    return
                use_yolo = False
        backend_name = "mediapipe" if use_mediapipe else "yolo" if use_yolo else "opencv"
        face_cascade = eye_cascade = None
        if not use_mediapipe and not use_yolo:
            cascades = _cascades(cv2)
            if cascades is None:
                payload = {
                    "available": False,
                    "backend": "opencv",
                    "reason": "OpenCV Haar cascades are unavailable.",
                    "eye_contact_intervals": [],
                    "green_label_count": 0,
                }
                self._write(target, payload)
                context.metadata["eye_contact"] = payload
                context.artifacts["eye_contact"] = str(target)
                context.warnings.append("Eye-contact detection skipped: cascades missing.")
                io.report(100, "Eye-contact analysis unavailable (cascade files missing)")
                return
            face_cascade, eye_cascade = cascades
        frames_dir = context.output / "vision" / "frames"
        io.report(5, "Extracting face samples")
        duration_seconds = (
            context.duration_samples() / max(1, context.media.audio_sample_rate)
            if context.media is not None
            else 0
        )
        timeout = max(600, min(7200, int(duration_seconds * 2 + 60)))
        try:
            frames = adapter_for(context, io).extract_frames(
                context.source,
                frames_dir,
                fps=options.sample_fps,
                width=options.width,
                max_frames=options.max_frames,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001 - optional analysis must not kill the job
            payload = {
                "available": False,
                "backend": backend_name,
                "reason": f"Frame extraction failed: {exc}",
                "eye_contact_intervals": [],
                "green_label_count": 0,
            }
            self._write(target, payload)
            context.metadata["eye_contact"] = payload
            context.artifacts["eye_contact"] = str(target)
            context.warnings.append(f"Eye-contact analysis failed: {exc}")
            io.report(100, "Eye-contact analysis failed; manual audit remains available")
            return
        frames = frames[: options.max_frames]
        hits: list[tuple[int, float]] = []
        total = max(1, len(frames))
        mesh = None
        if use_mediapipe and mediapipe is not None:
            mesh = mediapipe.solutions.face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
            )
        try:
            for index, frame_path in enumerate(frames, start=1):
                image = cv2.imread(str(frame_path))
                if image is None:
                    continue
                if mesh is not None:
                    eye_contact, confidence, _ratio = _analyze_mediapipe(
                        mesh,
                        cv2,
                        image,
                        min_face_ratio=options.min_face_ratio,
                        center_tolerance=options.center_tolerance,
                        min_eyes=options.min_eyes,
                    )
                elif yolo_model_obj is not None:
                    eye_contact, confidence, _ratio = _analyze_yolo(
                        yolo_model_obj,
                        image,
                        min_face_ratio=options.min_face_ratio,
                        center_tolerance=options.center_tolerance,
                        confidence=options.yolo_confidence,
                    )
                else:
                    eye_contact, confidence, _ratio = _analyze_frame(
                        cv2,
                        image,
                        face_cascade,
                        eye_cascade,
                        min_face_ratio=options.min_face_ratio,
                        center_tolerance=options.center_tolerance,
                        min_eyes=options.min_eyes,
                    )
                if eye_contact:
                    hits.append((index, confidence))
                io.report(5 + int(index / total * 85), f"Face sample {index}/{total}")
        finally:
            if mesh is not None:
                mesh.close()
        intervals = _merge_intervals(hits, fps=options.sample_fps)
        payload = {
            "available": True,
            "backend": backend_name,
            "sample_fps": options.sample_fps,
            "frames_analyzed": len(frames),
            "eye_contact_frames": len(hits),
            "eye_contact_intervals": intervals,
            "green_label_count": len(intervals),
            "green_labels": [
                {"start_sec": item["start_sec"], "end_sec": item["end_sec"]} for item in intervals
            ],
        }
        self._write(target, payload)
        context.metadata["eye_contact"] = payload
        context.artifacts["eye_contact"] = str(target)
        if options.write_markers:
            for index, interval in enumerate(intervals, start=1):
                add_marker(
                    context.output,
                    marker_id=f"eye-contact-{index:04d}",
                    time_sec=float(interval["start_sec"]),
                    end_sec=float(interval["end_sec"]),
                    label="Eye contact",
                    color="#00FF66",
                )
        context.hashes["vision.face_contact"] = digest_payload(
            {"intervals": len(intervals), "frames": len(frames)}
        )
        io.report(
            100,
            f"{len(intervals)} eye-contact span(s) across {len(frames)} frame(s)",
        )

    @staticmethod
    def _write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("eye_contact")
        return (Path(path),) if path else ()
