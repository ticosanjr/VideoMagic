"""Anchored callout cards and their timeline overlay attachment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.motion import find_font
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import StateNotReadyError
from videoflow.domain.state import OverlayClip
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _wrap(draw: Any, text: str, font: Any, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and draw.textlength(candidate, font=font) > width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines[:3]


def render_callout(
    text: str,
    target: Path,
    *,
    accent: str = "#FF3B30",
    text_color: str = "#F8FAFC",
) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 960, 260
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font_path = find_font()
    try:
        font = ImageFont.truetype(font_path, 44) if font_path else ImageFont.load_default()
    except OSError:
        font = ImageFont.load_default()
    draw.rounded_rectangle(
        (2, 2, width - 3, height - 3),
        radius=26,
        fill=(2, 6, 23, 225),
        outline=accent,
        width=4,
    )
    draw.rectangle((2, 2, 18, height - 3), fill=accent)
    lines = _wrap(draw, text, font, width - 90)
    y = (height - len(lines) * 58) / 2
    for line in lines:
        draw.text((48, y), line, font=font, fill=text_color)
        y += 58
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return target


class MotionCalloutParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    units_path: str = Field(default="storyboard/units.json", max_length=2000)
    ocr_path: str = Field(default="vision/ocr.json", max_length=2000)
    tracks_path: str = Field(default="vision/tracks.json", max_length=2000)
    style_path: str = Field(default="style/style-guide.json", max_length=2000)
    max_callouts: int = Field(default=40, ge=1, le=300)
    duration_sec: float = Field(default=3.2, ge=0.5, le=20.0)


def _style_colors(context: PipelineContext, path: str) -> tuple[str, str]:
    payload = _load(context.output / path, {})
    palette = [
        str(item)
        for item in (
            payload.get("palette", []) if isinstance(payload, dict) else []
        )
        if str(item).startswith("#")
    ]
    accent = palette[2] if len(palette) > 2 else "#FF3B30"
    text = palette[1] if len(palette) > 1 else "#F8FAFC"
    return accent, text


def _track_position(
    tracks: list[dict[str, Any]],
    *,
    text: str,
    at: float,
    width: int,
    height: int,
) -> tuple[float, float] | None:
    candidates = [
        item
        for item in tracks
        if isinstance(item, dict)
        and (not text or str(item.get("text") or "").casefold() in text.casefold())
    ] or [item for item in tracks if isinstance(item, dict)]
    for track in candidates:
        points = [item for item in track.get("points", []) if isinstance(item, dict)]
        if not points:
            continue
        point = min(points, key=lambda item: abs(float(item.get("time") or 0.0) - at))
        if width > 0 and height > 0:
            return (
                max(0.04, min(0.76, float(point.get("x") or 0.0) / width)),
                max(0.08, min(0.82, float(point.get("y") or 0.0) / height)),
            )
    return None


@register_step
class MotionCalloutStep(BaseStep):
    type = "motion.callout"
    title = "Anchored callouts"
    description = (
        "Turn OCR text and tracked positions into transparent callout cards with "
        "timed spans for the timeline."
    )
    status = "available"
    icon = "▣"
    color = "#f59e0b"
    params_model = MotionCalloutParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = MotionCalloutParams.model_validate(params)
        units_payload = _load(context.output / options.units_path, {})
        units = (
            units_payload.get("units", [])
            if isinstance(units_payload, dict)
            else units_payload
        )
        ocr = _load(context.output / options.ocr_path, {})
        tracks_payload = _load(context.output / options.tracks_path, {})
        tracks = (
            tracks_payload.get("tracks", [])
            if isinstance(tracks_payload, dict)
            else tracks_payload
        )
        accent, text_color = _style_colors(context, options.style_path)
        width = context.media.width if context.media is not None else 1920
        height = context.media.height if context.media is not None else 1080
        ocr_frames = ocr.get("frames", []) if isinstance(ocr, dict) else []
        callouts: list[dict[str, Any]] = []
        for unit in units if isinstance(units, list) else []:
            if not isinstance(unit, dict) or len(callouts) >= options.max_callouts:
                continue
            start = float(unit.get("start_sec") or 0.0)
            end = float(unit.get("end_sec") or start + options.duration_sec)
            text = str(unit.get("title") or "").strip()
            for frame in ocr_frames if isinstance(ocr_frames, list) else []:
                if not isinstance(frame, dict):
                    continue
                timestamp = float(frame.get("time_sec") or 0.0)
                if timestamp < start or timestamp > end:
                    continue
                boxes = [item for item in frame.get("boxes", []) if isinstance(item, dict)]
                if boxes:
                    text = str(boxes[0].get("text") or text)
                    break
            if not text:
                continue
            position = _track_position(
                tracks if isinstance(tracks, list) else [],
                text=text,
                at=start,
                width=width,
                height=height,
            )
            target = (
                context.output
                / "motion"
                / "callouts"
                / f"callout-{len(callouts) + 1:04d}.png"
            )
            try:
                render_callout(
                    text, target, accent=accent, text_color=text_color
                )
            except Exception as exc:  # noqa: BLE001 - Pillow is optional
                context.warnings.append(f"Callout render skipped: {exc}")
                continue
            duration = min(
                options.duration_sec, max(0.8, end - start)
            )
            width_ratio = max(0.28, min(0.62, len(text) / 46.0))
            x = position[0] if position else 0.08
            y = position[1] if position else 0.68
            anchor = (
                "top_left"
                if x < 0.33 and y < 0.33
                else "top_center"
                if y < 0.33
                else "top_right"
                if x > 0.67 and y < 0.33
                else "bottom_left"
                if x < 0.33 and y > 0.67
                else "bottom_center"
                if y > 0.67
                else "bottom_right"
                if x > 0.67
                else "center"
            )
            callouts.append(
                {
                    "callout_id": f"CALLOUT-{len(callouts) + 1:04d}",
                    "unit_id": unit.get("unit_id"),
                    "text": text,
                    "path": str(target),
                    "start_sec": round(start, 3),
                    "duration_sec": round(duration, 3),
                    "anchor": anchor,
                    "margin_x": 0,
                    "margin_y": 0,
                    "z": 20,
                    "width_ratio": round(width_ratio, 3),
                }
            )
            io.report(
                int(len(callouts) / max(1, len(units)) * 100),
                f"Callout {len(callouts)}",
            )
        target = context.output / "motion" / "callouts.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"callouts": callouts, "count": len(callouts)}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["motion_callouts"] = str(target)
        context.metadata["motion_callouts"] = {"count": len(callouts)}
        context.hashes["motion.callout"] = digest_payload(
            {"callouts": len(callouts)}
        )
        io.report(100, f"{len(callouts)} callout(s) prepared")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("motion_callouts")
        return (Path(path),) if path else ()


class MotionAttachParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    callouts_path: str = Field(default="motion/callouts.json", max_length=2000)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


@register_step
class MotionAttachStep(BaseStep):
    type = "motion.attach"
    title = "Attach overlays"
    description = (
        "Add approved callout cards to the project state so direct exports and "
        "NLE timelines include them."
    )
    status = "available"
    icon = "⊕"
    color = "#f59e0b"
    requires = ("edit.timeline", "motion.callout")
    params_model = MotionAttachParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = MotionAttachParams.model_validate(params)
        if context.state is None or context.media is None:
            raise StateNotReadyError("Overlay attachment requires the built timeline.")
        payload = _load(context.output / options.callouts_path, {})
        callouts = payload.get("callouts", []) if isinstance(payload, dict) else []
        media = context.media
        fps = media.fps_num / max(1, media.fps_den)
        kept = [
            item
            for item in context.state.overlays
            if not item.overlay_id.startswith("callout-")
        ]
        attached: list[dict[str, Any]] = []
        for index, callout in enumerate(callouts, start=1):
            if not isinstance(callout, dict):
                continue
            path = Path(str(callout.get("path") or ""))
            if not path.is_file():
                continue
            start_frame = max(0, int(round(float(callout.get("start_sec") or 0.0) * fps)))
            duration = max(
                1, int(round(float(callout.get("duration_sec") or 3.0) * fps))
            )
            overlay = OverlayClip(
                overlay_id=f"callout-{index:04d}",
                asset_id=str(callout.get("callout_id") or ""),
                path=str(path),
                start_frame=start_frame,
                duration_frames=duration,
                anchor=str(callout.get("anchor") or "bottom_left"),  # type: ignore[arg-type]
                margin_x=int(callout.get("margin_x") or 0),
                margin_y=int(callout.get("margin_y") or 0),
                z=int(callout.get("z") or 20),
                width_ratio=float(callout.get("width_ratio") or 0.4),
                opacity=options.opacity,
                kind="image",
            )
            kept.append(overlay)
            attached.append(overlay.model_dump(mode="json"))
        context.state.overlays = kept
        report = {"attached": len(attached), "overlays": attached}
        target = context.output / "motion" / "overlay-sync.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        context.artifacts["motion_attached"] = str(target)
        context.metadata["motion_attached"] = {"count": len(attached)}
        context.hashes["motion.attach"] = digest_payload({"count": len(attached)})
        io.report(100, f"{len(attached)} callout overlay(s) attached")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("motion_attached")
        return (Path(path),) if path else ()


class CompositeMatteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments_path: str = Field(default="vision/segments.json", max_length=2000)
    output_name: str = Field(default="matte-plan.json", max_length=200)


@register_step
class CompositeMatteStep(BaseStep):
    type = "composite.matte"
    title = "Matte plan"
    description = (
        "Validate the subject masks and write the matte compositing plan. The "
        "masked composite itself stays an NLE-reviewed operation."
    )
    status = "available"
    icon = "◧"
    color = "#22c55e"
    requires = ("vision.segment",)
    params_model = CompositeMatteParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = CompositeMatteParams.model_validate(params)
        payload = _load(context.output / options.segments_path, {})
        masks = [
            item
            for item in (
                payload.get("masks", []) if isinstance(payload, dict) else payload
            )
            if isinstance(item, dict) and item.get("mask")
        ]
        plan = {
            "status": "review" if masks else "manual",
            "masks": masks,
            "note": (
                "Subject masks are ready for an NLE matte composite. "
                "Automatic behind-subject compositing is not applied to the MP4."
            ),
        }
        target = context.output / "motion" / options.output_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        context.artifacts["matte_plan"] = str(target)
        context.metadata["matte_plan"] = plan
        context.hashes["composite.matte"] = digest_payload(
            {"masks": len(masks)}
        )
        if not masks:
            context.warnings.append(
                "No subject mask is available; use the NLE or the vision gate."
            )
        io.report(100, f"Matte plan ready ({len(masks)} mask(s))")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("matte_plan")
        return (Path(path),) if path else ()


__all__ = [
    "CompositeMatteParams",
    "CompositeMatteStep",
    "MotionAttachParams",
    "MotionAttachStep",
    "MotionCalloutParams",
    "MotionCalloutStep",
    "render_callout",
]
