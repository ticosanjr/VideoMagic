"""Fuse scenes with decupage ASUs into a timeline supercontext."""

from __future__ import annotations

from typing import Any

from videoflow.application.scene_intel.layout import protected_from_broll
from videoflow.domain.scenes import SceneEntry, ScenesManifest


def _midpoint(start: float, end: float) -> float:
    return start + max(0.0, end - start) / 2.0


def _scene_for(
    scenes: list[SceneEntry],
    start_sec: float,
    end_sec: float,
) -> SceneEntry | None:
    point = _midpoint(start_sec, end_sec)
    for scene in scenes:
        if scene.start_sec <= point < scene.end_sec:
            return scene
    if not scenes:
        return None
    # An ASU beyond the last boundary belongs to the final scene.
    return scenes[-1] if point >= scenes[-1].end_sec else scenes[0]


def _asus_from_plan(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        return []
    raw = plan.get("asus")
    if isinstance(raw, list) and raw:
        return [item for item in raw if isinstance(item, dict)]
    raw = plan.get("active_spans")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _asus_from_context(asus: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [item for item in (asus or []) if isinstance(item, dict)]


def _cut_spans(plan: dict[str, Any] | None, sample_rate: int) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        return []
    cuts = plan.get("cuts")
    if not isinstance(cuts, list):
        return []
    rate = max(1, int(plan.get("sample_rate") or sample_rate or 48_000))
    spans: list[dict[str, Any]] = []
    for cut in cuts:
        if not isinstance(cut, dict):
            continue
        start_sec = float(cut.get("start_sec", int(cut.get("start_sample", 0)) / rate))
        end_sec = float(cut.get("end_sec", int(cut.get("end_sample", 0)) / rate))
        spans.append(
            {
                "start_sec": round(start_sec, 6),
                "end_sec": round(end_sec, 6),
                "reason": str(cut.get("reason") or "remove"),
                "asu_id": str(cut.get("asu_id") or ""),
                "needs_broll_or_punch_in": bool(cut.get("needs_broll_or_punch_in")),
            }
        )
    return spans


def build_supercontext(
    manifest: ScenesManifest,
    *,
    asus: list[dict[str, Any]] | None = None,
    decupage_plan: dict[str, Any] | None = None,
    sample_rate: int = 48_000,
) -> dict[str, Any]:
    """Return a compact, render-ready view of scenes plus spoken units."""

    scenes = sorted(manifest.scenes, key=lambda item: item.start_sample)
    merged: list[dict[str, Any]] = []
    for asu in _asus_from_plan(decupage_plan) + _asus_from_context(asus):
        asu_id = str(asu.get("asu_id") or "")
        if not asu_id:
            continue
        start = float(asu.get("start_sec", 0.0))
        end = float(asu.get("end_sec", start))
        scene = _scene_for(scenes, start, end)
        if scene is None:
            continue
        protected = protected_from_broll(scene.layout_type, scene.editing_hints)
        merged.append(
            {
                "asu_id": asu_id,
                "text": str(asu.get("text") or ""),
                "start_sec": round(start, 6),
                "end_sec": round(end, 6),
                "duration_sec": round(max(0.0, end - start), 6),
                "scene_id": scene.scene_id,
                "layout_type": scene.layout_type,
                "editing_hints": list(scene.editing_hints),
                "broll_allowed": not protected,
                "protected_from_broll": protected,
                "face_bbox_norm": (
                    scene.face_bbox_norm.model_dump() if scene.face_bbox_norm else None
                ),
                "scene_start_sec": scene.start_sec,
                "scene_end_sec": scene.end_sec,
            }
        )
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in merged:
        key = item["asu_id"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    warnings: list[str] = []
    if not unique:
        warnings.append("No ASUs were available; supercontext lists scenes only.")
    return {
        "schema_version": 1,
        "video_id": manifest.video_id,
        "source_topology": manifest.source_topology,
        "resolution": dict(manifest.resolution),
        "fps_num": manifest.fps_num,
        "fps_den": manifest.fps_den,
        "scenes": [
            {
                "scene_id": scene.scene_id,
                "start_sec": scene.start_sec,
                "end_sec": scene.end_sec,
                "duration_sec": round(scene.end_sec - scene.start_sec, 6),
                "layout_type": scene.layout_type,
                "editing_hints": list(scene.editing_hints),
                "protected_from_broll": protected_from_broll(
                    scene.layout_type, scene.editing_hints
                ),
                "face_bbox_norm": (
                    scene.face_bbox_norm.model_dump() if scene.face_bbox_norm else None
                ),
                "keyframe_path": scene.keyframe_path,
            }
            for scene in scenes
        ],
        "asus": unique,
        "cut_spans": _cut_spans(decupage_plan, sample_rate),
        "warnings": warnings,
    }


def planner_payload(supercontext: dict[str, Any]) -> dict[str, Any]:
    """LLM-safe view: ids, text, layout, durations, and hints only.

    Absolute start/end times stay local; the planner chooses scene ids and the
    Python layer converts them into render timestamps.
    """

    return {
        "source_topology": supercontext.get("source_topology", "single_16x9"),
        "scenes": [
            {
                "scene_id": item["scene_id"],
                "layout_type": item["layout_type"],
                "duration_sec": item["duration_sec"],
                "editing_hints": item.get("editing_hints", []),
                "protected_from_broll": item.get("protected_from_broll", False),
            }
            for item in supercontext.get("scenes", [])
        ],
        "asus": [
            {
                "asu_id": item["asu_id"],
                "scene_id": item["scene_id"],
                "text": item.get("text", ""),
                "duration_sec": item["duration_sec"],
                "broll_allowed": item.get("broll_allowed", True),
            }
            for item in supercontext.get("asus", [])
        ],
    }


__all__ = ["build_supercontext", "planner_payload"]
