"""OCR, subject masks, and motion tracking steps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.vision_analysis import (
    extract_frames,
    ocr_boxes,
    segmentation_mask,
    track_box,
)
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _frame_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        return (0, 0)


class VisionOcrParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_fps: float = Field(default=1.0, gt=0.0, le=10.0)
    max_frames: int = Field(default=120, ge=1, le=2000)
    width: int = Field(default=1280, ge=160, le=3840)
    language: str = Field(default="por+eng", max_length=40)
    min_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    backend: Literal["auto", "tesseract", "none"] = "auto"


@register_step
class VisionOcrStep(BaseStep):
    type = "vision.ocr"
    title = "OCR coordinates"
    description = (
        "Detect on-screen text and bounding boxes from sampled frames so callouts "
        "can point at the exact printed word."
    )
    status = "available"
    icon = "T"
    color = "#f59e0b"
    requires = ("ingest",)
    params_model = VisionOcrParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = VisionOcrParams.model_validate(params)
        frames = extract_frames(
            context.source,
            context.output / "vision" / "frames",
            fps=options.sample_fps,
            max_frames=options.max_frames,
            width=options.width,
        )
        result: list[dict[str, Any]] = []
        empty = 0
        for index, frame in enumerate(frames, start=1):
            boxes = (
                []
                if options.backend == "none"
                else ocr_boxes(
                    frame,
                    language=options.language,
                    min_confidence=options.min_confidence,
                )
            )
            if not boxes:
                empty += 1
            width, height = _frame_size(frame)
            result.append(
                {
                    "frame": frame.name,
                    "time_sec": round(index / max(0.01, options.sample_fps), 3),
                    "width": width,
                    "height": height,
                    "boxes": boxes,
                }
            )
            io.report(int(index / max(1, len(frames)) * 100), f"OCR frame {index}")
        target = context.output / "vision" / "ocr.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"frames": result, "count": len(result)}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["vision_ocr"] = str(target)
        context.metadata["vision_ocr"] = {
            "frames": len(result),
            "frames_without_text": empty,
        }
        context.hashes["vision.ocr"] = digest_payload(
            {"frames": len(result), "empty": empty}
        )
        if result and empty == len(result):
            context.warnings.append(
                "OCR found no text; install pytesseract/tesseract or add boxes manually."
            )
        io.report(100, f"{len(result)} frame(s) scanned; {empty} without text")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("vision_ocr")
        return (Path(path),) if path else ()


class VisionSegmentParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_fps: float = Field(default=0.5, gt=0.0, le=5.0)
    max_frames: int = Field(default=60, ge=1, le=600)
    width: int = Field(default=960, ge=160, le=3840)
    backend: Literal["auto", "mediapipe", "grabcut", "none"] = "auto"


@register_step
class VisionSegmentStep(BaseStep):
    type = "vision.segment"
    title = "Subject masks"
    description = (
        "Create foreground masks for sampled frames. MediaPipe or GrabCut is "
        "optional; the gate still works without a mask."
    )
    status = "available"
    icon = "◐"
    color = "#22c55e"
    requires = ("ingest",)
    params_model = VisionSegmentParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = VisionSegmentParams.model_validate(params)
        frames = extract_frames(
            context.source,
            context.output / "vision" / "frames",
            fps=options.sample_fps,
            max_frames=options.max_frames,
            width=options.width,
        )
        masks: list[dict[str, Any]] = []
        backends: set[str] = set()
        for index, frame in enumerate(frames, start=1):
            mask_path, used = segmentation_mask(
                frame,
                context.output / "vision" / "masks" / f"{frame.stem}.png",
                backend=options.backend,
            )
            backends.add(used)
            masks.append(
                {
                    "frame": frame.name,
                    "time_sec": round(index / max(0.01, options.sample_fps), 3),
                    "mask": str(mask_path) if mask_path else "",
                    "backend": used,
                }
            )
            io.report(int(index / max(1, len(frames)) * 100), f"Mask {index}")
        target = context.output / "vision" / "segments.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"masks": masks, "count": len(masks)}, indent=2) + "\n",
            encoding="utf-8",
        )
        context.artifacts["vision_segments"] = str(target)
        context.metadata["vision_segments"] = {
            "frames": len(masks),
            "backends": sorted(backends),
        }
        context.hashes["vision.segment"] = digest_payload(
            {"frames": len(masks), "backends": sorted(backends)}
        )
        if backends == {"none"}:
            context.warnings.append(
                "Subject segmentation unavailable; overlays will render in front."
            )
        io.report(100, f"{len(masks)} mask(s) prepared")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("vision_segments")
        return (Path(path),) if path else ()


class VisionTrackParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ocr_path: str = Field(default="vision/ocr.json", max_length=2000)
    max_tracks: int = Field(default=12, ge=1, le=100)
    sample_fps: float = Field(default=2.0, gt=0.0, le=15.0)
    max_seconds: float = Field(default=0.0, ge=0.0, le=3600.0)


@register_step
class VisionTrackStep(BaseStep):
    type = "vision.track"
    title = "Track on-screen text"
    description = (
        "Track OCR boxes across frames with pyramidal Lucas-Kanade so callouts "
        "stay anchored to the moving word or object."
    )
    status = "available"
    icon = "◎"
    color = "#22c55e"
    requires = ("ingest", "vision.ocr")
    params_model = VisionTrackParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = VisionTrackParams.model_validate(params)
        payload = _load(context.output / options.ocr_path, {})
        frames = payload.get("frames", []) if isinstance(payload, dict) else []
        source_width = context.media.width if context.media is not None else 0
        tracks: list[dict[str, Any]] = []
        seen: set[str] = set()
        for frame in frames if isinstance(frames, list) else []:
            for box in frame.get("boxes", []) if isinstance(frame, dict) else []:
                if not isinstance(box, dict):
                    continue
                text = str(box.get("text") or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                frame_width = int(frame.get("width") or 0) or source_width or 1
                scale = source_width / frame_width if source_width else 1.0
                bbox = (
                    int(float(box.get("x") or 0) * scale),
                    int(float(box.get("y") or 0) * scale),
                    max(2, int(float(box.get("width") or 2) * scale)),
                    max(2, int(float(box.get("height") or 2) * scale)),
                )
                points = track_box(
                    context.source,
                    bbox,
                    start_sec=float(frame.get("time_sec") or 0.0),
                    end_sec=options.max_seconds,
                    fps=options.sample_fps,
                )
                tracks.append(
                    {
                        "text": text,
                        "box": bbox,
                        "start_sec": float(frame.get("time_sec") or 0.0),
                        "points": points,
                    }
                )
                if len(tracks) >= options.max_tracks:
                    break
            if len(tracks) >= options.max_tracks:
                break
        target = context.output / "vision" / "tracks.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"tracks": tracks, "count": len(tracks)}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["vision_tracks"] = str(target)
        context.metadata["vision_tracks"] = {"count": len(tracks)}
        context.hashes["vision.track"] = digest_payload({"tracks": len(tracks)})
        io.report(100, f"{len(tracks)} track(s) prepared")
        if not tracks:
            context.warnings.append(
                "No tracking boxes were available; callouts will use fixed positions."
            )

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("vision_tracks")
        return (Path(path),) if path else ()


__all__ = [
    "VisionOcrParams",
    "VisionOcrStep",
    "VisionSegmentParams",
    "VisionSegmentStep",
    "VisionTrackParams",
    "VisionTrackStep",
]
