"""Deterministic and LLM-facing Short planners."""

from __future__ import annotations

from typing import Any

from videoflow.application.short_composition.plan import overlapping_scenes
from videoflow.domain.errors import ShortPlanError
from videoflow.domain.scenes import ScenesManifest
from videoflow.domain.short_composition import (
    ShortCompositionDraft,
    ShortPlanResponse,
    ShortSegmentDraft,
)

LAYOUT_BY_SCENE = {
    "TALKING_HEAD": "FULL_FACE",
    "BROLL_OR_FOOTAGE": "FULL_FACE",
    "SCREEN_SHARE_PIP": "SPLIT_SCREEN_SAFE",
    "SCREEN_SHARE_FULL": "SPLIT_SCREEN_SAFE",
    "DUAL_CANVAS_OBS": "SPLIT_SCREEN_SAFE",
}


def default_window(
    manifest: ScenesManifest,
    *,
    start_sec: float = 0.0,
    end_sec: float = 0.0,
    max_sec: float = 60.0,
) -> tuple[float, float]:
    duration = max(
        (scene.end_sec for scene in manifest.scenes),
        default=0.0,
    )
    start = max(0.0, min(float(start_sec), duration))
    if end_sec and end_sec > start:
        end = min(float(end_sec), duration)
    else:
        end = min(duration, start + max(1.0, float(max_sec)))
    if end <= start:
        raise ShortPlanError("scene manifest does not cover a positive Short range")
    return start, end


def deterministic_draft(
    manifest: ScenesManifest,
    *,
    short_id: str,
    start_sec: float = 0.0,
    end_sec: float = 0.0,
    max_sec: float = 60.0,
) -> ShortCompositionDraft:
    """Map scene types to safe layouts without inventing B-roll."""

    start, end = default_window(
        manifest,
        start_sec=start_sec,
        end_sec=end_sec,
        max_sec=max_sec,
    )
    scenes = overlapping_scenes(manifest.scenes, start, end)
    if not scenes:
        raise ShortPlanError("no scenes overlap the requested Short range")
    segments: list[ShortSegmentDraft] = []
    for index, scene in enumerate(scenes, start=1):
        layout = LAYOUT_BY_SCENE.get(scene.layout_type, "FULL_FACE")
        segments.append(
            ShortSegmentDraft(
                seg_id=f"S{index:02d}",
                start_scene_id=scene.scene_id,
                end_scene_id=scene.scene_id,
                layout=layout,  # type: ignore[arg-type]
                face_zoom=1.0,
            )
        )
    return ShortCompositionDraft(
        short_id=short_id,
        source_topology=manifest.source_topology,
        start=start,
        end=end,
        segments=segments,
    )


def build_llm_request(
    supercontext: dict[str, Any],
    *,
    short_id: str,
    start_sec: float,
    end_sec: float,
    min_segment_sec: float = 2.5,
) -> dict[str, Any]:
    """ID-only request. Absolute timestamps never leave the process."""

    def overlaps(item: dict[str, Any]) -> bool:
        try:
            return float(item["end_sec"]) > start_sec and float(item["start_sec"]) < end_sec
        except (KeyError, TypeError, ValueError):
            return False

    scenes = [
        {
            "scene_id": item["scene_id"],
            "layout_type": item["layout_type"],
            "duration_sec": item["duration_sec"],
            "editing_hints": item.get("editing_hints", []),
            "protected_from_broll": item.get("protected_from_broll", False),
        }
        for item in supercontext.get("scenes", [])
        if overlaps(item)
    ]
    asus = [
        {
            "asu_id": item["asu_id"],
            "scene_id": item["scene_id"],
            "text": item.get("text", ""),
            "duration_sec": item["duration_sec"],
            "broll_allowed": item.get("broll_allowed", True),
        }
        for item in supercontext.get("asus", [])
        if overlaps(
            {
                "start_sec": item.get("start_sec", 0.0),
                "end_sec": item.get("end_sec", 0.0),
            }
        )
    ]
    return {
        "schema": "short_composition_v1",
        "instructions": (
            "Return segments using scene ids only. Cover the full duration with "
            "contiguous segments and no overlaps. Never invent timestamps."
        ),
        "short_id": short_id,
        "source_topology": supercontext.get("source_topology", "single_16x9"),
        "total_duration_sec": round(max(0.0, end_sec - start_sec), 3),
        "min_segment_sec": min_segment_sec,
        "layouts": [
            "FULL_FACE",
            "SPLIT_BROLL",
            "SPLIT_SCREEN_SAFE",
            "SPLIT_SCREEN_FILL",
        ],
        "scenes": scenes,
        "asus": asus,
    }


def plan_prompt(request: dict[str, Any]) -> str:
    import json

    return (
        "You compose vertical Shorts. Use only scene_id/asu_id anchors; do not "
        "emit absolute timestamps. Every segment needs start_scene_id and "
        "end_scene_id, a layout, and face_zoom between 1.0 and 1.12. Never use "
        "SPLIT_BROLL on protected_from_broll scenes. Return JSON with keys "
        "short_id and segments. Request:\n"
        + json.dumps(request, ensure_ascii=False)
    )


def parse_llm_response(
    raw: dict[str, Any],
    *,
    short_id: str,
    start_sec: float,
    end_sec: float,
    source_topology: str = "single_16x9",
) -> ShortCompositionDraft:
    try:
        response = ShortPlanResponse.model_validate(raw)
    except ValueError as exc:
        raise ShortPlanError(f"invalid Short plan response: {exc}") from exc
    if not response.segments:
        raise ShortPlanError("Short plan response has no segments")
    return ShortCompositionDraft(
        short_id=response.short_id or short_id,
        source_topology=source_topology,  # type: ignore[arg-type]
        start=start_sec,
        end=end_sec,
        segments=response.segments,
    )


__all__ = [
    "LAYOUT_BY_SCENE",
    "build_llm_request",
    "default_window",
    "deterministic_draft",
    "parse_llm_response",
    "plan_prompt",
]
