"""Resolve drafts into a strict, render-ready Short composition plan."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from videoflow.application.short_composition.broll import validate_broll
from videoflow.application.short_composition.geometry import (
    MAX_FACE_UPSCALE,
    CropBox,
    crop_for_panel,
    face_box_from_norm,
    layout_geometry,
    upscale_ratio,
)
from videoflow.application.short_composition.tracking import (
    CropSample,
    scene_crop_samples,
    static_crop,
)
from videoflow.domain.errors import ShortPlanError
from videoflow.domain.scenes import SceneEntry, ScenesManifest
from videoflow.domain.short_composition import (
    ShortCompositionDraft,
    ShortCompositionPlan,
    ShortSegment,
)

MIN_SEGMENT_SEC = 2.5
_EPS = 1e-6


@dataclass
class PlannedCrop:
    seg_id: str
    static: CropBox
    samples: list[CropSample] = field(default_factory=list)
    upscale: float = 1.0


@dataclass
class ResolutionResult:
    plan: ShortCompositionPlan
    warnings: list[str]
    crops: dict[str, PlannedCrop]
    report: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": True,
            "plan": self.plan.model_dump(mode="json"),
            "warnings": list(self.warnings),
            "report": dict(self.report),
        }


@dataclass
class _RawSegment:
    seg_id: str
    start: float
    end: float
    source: object

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def _scene_index(manifest: ScenesManifest) -> dict[str, SceneEntry]:
    return {scene.scene_id: scene for scene in manifest.scenes}


def _anchor_start(segment: object, scenes: dict[str, SceneEntry], plan_start: float) -> float:
    rel = getattr(segment, "rel_start", None)
    if rel is not None:
        return float(rel)
    scene_id = str(getattr(segment, "start_scene_id", "") or "")
    scene = scenes.get(scene_id)
    if scene is None:
        raise ShortPlanError(f"{getattr(segment, 'seg_id', '?')}: unknown scene {scene_id!r}")
    return scene.start_sec - plan_start


def _anchor_end(segment: object, scenes: dict[str, SceneEntry], plan_start: float) -> float:
    rel = getattr(segment, "rel_end", None)
    if rel is not None:
        return float(rel)
    scene_id = str(getattr(segment, "end_scene_id", "") or "")
    scene = scenes.get(scene_id)
    if scene is None:
        raise ShortPlanError(f"{getattr(segment, 'seg_id', '?')}: unknown scene {scene_id!r}")
    return scene.end_sec - plan_start


def overlapping_scenes(
    scenes: list[SceneEntry],
    start_sec: float,
    end_sec: float,
) -> list[SceneEntry]:
    return [
        scene
        for scene in scenes
        if scene.end_sec > start_sec + _EPS and scene.start_sec < end_sec - _EPS
    ]


def is_protected(scene: SceneEntry) -> bool:
    return "PROTECT_FROM_BROLL" in scene.editing_hints or scene.layout_type in {
        "SCREEN_SHARE_PIP",
        "SCREEN_SHARE_FULL",
        "DUAL_CANVAS_OBS",
    }


def _dominant_scene(
    scenes: list[SceneEntry],
    start_sec: float,
    end_sec: float,
) -> SceneEntry | None:
    best: SceneEntry | None = None
    best_overlap = 0.0
    for scene in overlapping_scenes(scenes, start_sec, end_sec):
        overlap = min(scene.end_sec, end_sec) - max(scene.start_sec, start_sec)
        if overlap > best_overlap:
            best = scene
            best_overlap = overlap
    return best


def camera_size(manifest: ScenesManifest) -> tuple[int, int]:
    width = int(manifest.resolution.get("w") or 1920)
    height = int(manifest.resolution.get("h") or 1080)
    if manifest.source_topology == "dual_canvas":
        width = max(1, width // 2)
    return width, height


def _face_payload(scene: SceneEntry | None) -> dict[str, float] | None:
    if scene is None or scene.face_bbox_norm is None:
        return None
    return scene.face_bbox_norm.model_dump()


def _warn(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)


def resolve_draft(
    draft: ShortCompositionDraft,
    manifest: ScenesManifest,
    *,
    min_segment_sec: float = MIN_SEGMENT_SEC,
    smooth_track: bool = False,
    max_upscale: float = MAX_FACE_UPSCALE,
    broll_exists: Callable[[Path], bool] | None = None,
) -> ResolutionResult:
    """Convert scene ids/times into a contiguous plan and validate it."""

    scenes = sorted(manifest.scenes, key=lambda item: item.start_sample)
    index = _scene_index(manifest)
    duration = draft.duration_sec
    if duration <= 0:
        raise ShortPlanError("plan duration must be positive")
    minimum = max(0.0, float(min_segment_sec))
    warnings: list[str] = []
    raw: list[_RawSegment] = []
    for segment in draft.segments:
        start = _anchor_start(segment, index, draft.start)
        end = _anchor_end(segment, index, draft.start)
        if end <= start:
            raise ShortPlanError(f"{segment.seg_id}: end must be after start")
        raw.append(_RawSegment(segment.seg_id, start, end, segment))
    raw.sort(key=lambda item: item.start)

    for previous, current in zip(raw, raw[1:], strict=False):
        if current.start < previous.end - 1e-5:
            raise ShortPlanError(
                f"segments overlap: {previous.seg_id} ends at {previous.end:.3f}, "
                f"{current.seg_id} starts at {current.start:.3f}"
            )

    for item in raw:
        if item.start < -_EPS:
            item.start = 0.0
            _warn(warnings, f"{item.seg_id}: start clamped to 0")
        if item.end > duration + _EPS:
            item.end = duration
            _warn(warnings, f"{item.seg_id}: end clamped to plan duration")
    raw = [item for item in raw if item.end - item.start > _EPS]
    if not raw:
        raise ShortPlanError("no segment remains after clamping to the plan range")

    if raw[0].start > _EPS:
        _warn(warnings, f"{raw[0].seg_id}: leading gap filled")
        raw[0].start = 0.0
    for previous, current in zip(raw, raw[1:], strict=False):
        if current.start - previous.end > _EPS:
            _warn(warnings, f"gap filled between {previous.seg_id} and {current.seg_id}")
            previous.end = current.start
    if raw[-1].end < duration - _EPS:
        _warn(warnings, f"{raw[-1].seg_id}: trailing gap filled")
        raw[-1].end = duration

    changed = True
    while changed:
        changed = False
        for position, item in enumerate(raw):
            if item.end - item.start >= minimum - _EPS:
                continue
            if position > 0:
                raw[position - 1].end = item.end
                _warn(
                    warnings,
                    f"{item.seg_id}: shorter than {minimum:g}s, merged into "
                    f"{raw[position - 1].seg_id}",
                )
                del raw[position]
            elif len(raw) > 1:
                raw[1].start = item.start
                _warn(
                    warnings,
                    f"{item.seg_id}: shorter than {minimum:g}s, merged into {raw[1].seg_id}",
                )
                del raw[0]
            else:
                raise ShortPlanError(
                    f"plan duration {duration:.2f}s is below the minimum segment "
                    f"length {minimum:g}s"
                )
            changed = True
            break

    cam_w, cam_h = camera_size(manifest)
    plan_segments: list[ShortSegment] = []
    crops: dict[str, PlannedCrop] = {}
    for item in raw:
        source = item.source
        source_start = draft.start + item.start
        source_end = draft.start + item.end
        touched = overlapping_scenes(scenes, source_start, source_end)
        protected = [scene for scene in touched if is_protected(scene)]
        layout = str(source.layout)
        broll = getattr(source, "broll_source", None)
        if layout == "SPLIT_BROLL" and protected:
            layout = "SPLIT_SCREEN_SAFE"
            broll = None
            _warn(
                warnings,
                f"{item.seg_id}: B-roll blocked by protected scene; "
                "using SPLIT_SCREEN_SAFE",
            )
        if layout == "SPLIT_BROLL":
            exists = None
            if broll_exists is not None and broll is not None and broll.path:
                exists = broll_exists(Path(broll.path).expanduser())
            check = validate_broll(broll, is_file=exists)
            if not check.ok:
                layout = "FULL_FACE"
                broll = None
                _warn(
                    warnings,
                    f"{item.seg_id}: B-roll unavailable ({check.reason}); using FULL_FACE",
                )
        dominant = _dominant_scene(scenes, source_start, source_end)
        segment = ShortSegment(
            seg_id=item.seg_id,
            rel_start=round(item.start, 6),
            rel_end=round(item.end, 6),
            layout=layout,  # type: ignore[arg-type]
            face_zoom=float(getattr(source, "face_zoom", 1.0)),
            broll_source=broll,
            screen_focus=getattr(source, "screen_focus", None),
            sfx_on_enter=getattr(source, "sfx_on_enter", None),
            start_scene_id=str(getattr(source, "start_scene_id", "") or ""),
            end_scene_id=str(getattr(source, "end_scene_id", "") or ""),
        )
        geometry = layout_geometry(segment.layout)
        sample_scenes = [
            {
                "start_sec": scene.start_sec,
                "face_bbox_norm": _face_payload(scene),
            }
            for scene in (touched or ([dominant] if dominant is not None else []))
        ]
        samples = scene_crop_samples(
            sample_scenes,
            cam_w=cam_w,
            cam_h=cam_h,
            layout=segment.layout,
            zoom=segment.face_zoom,
            smooth=smooth_track,
        )
        static = static_crop(samples)
        if static is None:
            static = crop_for_panel(
                cam_w=cam_w,
                cam_h=cam_h,
                panel=geometry.face,
                face=None,
                zoom=segment.face_zoom,
            )
        ratio = upscale_ratio(static.width, geometry.face.width)
        if ratio > max_upscale and segment.layout.startswith("SPLIT_SCREEN"):
            _warn(
                warnings,
                f"{item.seg_id}: PIP_LOW_RES_WARNING ({ratio:.2f}x); "
                "falling back to FULL_FACE",
            )
            segment = segment.model_copy(update={"layout": "FULL_FACE"})
            static = crop_for_panel(
                cam_w=cam_w,
                cam_h=cam_h,
                panel=layout_geometry("FULL_FACE").face,
                face=face_box_from_norm(_face_payload(dominant)),
                zoom=1.0,
            )
            ratio = upscale_ratio(static.width)
        crops[segment.seg_id] = PlannedCrop(
            seg_id=segment.seg_id,
            static=static,
            samples=samples,
            upscale=ratio,
        )
        plan_segments.append(segment)

    try:
        plan = ShortCompositionPlan(
            short_id=draft.short_id,
            source_video_path=draft.source_video_path,
            source_topology=draft.source_topology,
            start=draft.start,
            end=draft.end,
            end_padding_ms=draft.end_padding_ms,
            target_fps=draft.target_fps,
            subtitle_style=draft.subtitle_style,
            target_width=draft.target_width,
            target_height=draft.target_height,
            segments=plan_segments,
        )
    except ValueError as exc:
        raise ShortPlanError(str(exc)) from exc
    report: dict[str, object] = {
        "duration_sec": round(duration, 6),
        "segments": [
            {
                "seg_id": segment.seg_id,
                "rel_start": segment.rel_start,
                "rel_end": segment.rel_end,
                "layout": segment.layout,
                "upscale": crops[segment.seg_id].upscale,
                "crop": asdict(crops[segment.seg_id].static),
            }
            for segment in plan.segments
        ],
    }
    return ResolutionResult(plan=plan, warnings=warnings, crops=crops, report=report)


__all__ = [
    "MIN_SEGMENT_SEC",
    "PlannedCrop",
    "ResolutionResult",
    "camera_size",
    "is_protected",
    "overlapping_scenes",
    "resolve_draft",
]
