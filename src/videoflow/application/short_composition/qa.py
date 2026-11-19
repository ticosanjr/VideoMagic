"""Delivery QA for a composed Short."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from videoflow.application.short_composition.geometry import (
    SAFE_ZONES,
    CanvasRegion,
    caption_region,
    layout_geometry,
)
from videoflow.domain.short_composition import ShortCompositionPlan


def _caption_boxes(cues: dict[str, Any]) -> list[dict[str, Any]]:
    boxes: list[dict[str, Any]] = []
    for index, block in enumerate(cues.get("captions") or []):
        if not isinstance(block, dict):
            continue
        layout = str(block.get("layout") or "FULL_FACE")
        lines = block.get("lines") or ["x"]
        region = caption_region(layout, lines=len(lines))
        raw_y = block.get("subtitle_y")
        if raw_y is not None:
            with contextlib.suppress(TypeError, ValueError):
                region = CanvasRegion(
                    x=region.x,
                    y=int(float(raw_y)) - region.height // 2,
                    width=region.width,
                    height=region.height,
                )
        collisions = [
            name for name, zone in SAFE_ZONES.items() if region.overlaps(zone)
        ]
        boxes.append(
            {
                "index": index,
                "start": float(block.get("start") or 0.0),
                "end": float(block.get("end") or 0.0),
                "text": str(block.get("text") or ""),
                "layout": layout,
                "region": {
                    "x": region.x,
                    "y": region.y,
                    "width": region.width,
                    "height": region.height,
                },
                "safe_zone_collisions": collisions,
            }
        )
    return boxes


def validate_short_delivery(
    plan: ShortCompositionPlan,
    cues: dict[str, Any],
    *,
    render_path: Path | None,
    render_width: int = 0,
    render_height: int = 0,
    render_duration: float = 0.0,
    fcpxml_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    ending = cues.get("ending") if isinstance(cues.get("ending"), dict) else {}
    expected_end = float(
        ending.get("effective_end_sec")
        or plan.duration_sec + plan.end_padding_ms / 1000.0
    )
    if render_path is None or not Path(render_path).is_file():
        errors.append("rendered Short is missing")
    else:
        if (render_width, render_height) != (1080, 1920):
            errors.append(
                f"rendered canvas is {render_width}x{render_height}, expected 1080x1920"
            )
        if render_duration and abs(render_duration - expected_end) > 0.2:
            errors.append(
                f"rendered duration {render_duration:.2f}s differs from "
                f"expected {expected_end:.2f}s"
            )
    boxes = _caption_boxes(cues)
    for box in boxes:
        if box["safe_zone_collisions"]:
            errors.append(
                f"caption {box['index']} enters safe zone(s): "
                + ", ".join(box["safe_zone_collisions"])
            )
        if box["end"] <= box["start"]:
            errors.append(f"caption {box['index']} has an invalid span")
        if box["end"] > expected_end + 0.05:
            errors.append(
                f"caption {box['index']} ends after the rendered Short "
                f"({box['end']:.2f}s > {expected_end:.2f}s)"
            )
    ordered = sorted(boxes, key=lambda item: item["start"])
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current["start"] < previous["end"] - 1e-6:
            errors.append(
                f"captions overlap: {previous['index']} and {current['index']}"
            )
    for segment in plan.segments:
        geometry = layout_geometry(segment.layout)
        if geometry.face.bottom > 1920 or geometry.face.right > 1080:
            errors.append(f"{segment.seg_id}: face panel exceeds the canvas")
    if fcpxml_report is not None and not fcpxml_report.get("ok", False):
        for item in fcpxml_report.get("errors") or []:
            errors.append(f"FCPXML: {item}")
    for source in (cues.get("warnings"), (fcpxml_report or {}).get("warnings")):
        if isinstance(source, list):
            warnings.extend(str(item) for item in source)
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "duration_sec": round(expected_end, 3),
        "render_duration_sec": round(render_duration, 3),
        "captions": boxes,
        "segment_count": len(plan.segments),
        "tracks": {
            "V1": 1,
            "V2": len(fcpxml_report.get("face_clips") or []) if fcpxml_report else 0,
            "A1": len(plan.segments),
            "A2": len((fcpxml_report or {}).get("sfx") or []),
        },
    }


__all__ = ["validate_short_delivery"]
