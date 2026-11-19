"""Independent validation for a resolved Short composition plan."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from videoflow.application.short_composition.broll import validate_broll
from videoflow.application.short_composition.geometry import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    MAX_FACE_UPSCALE,
    captions_are_safe,
    face_box_from_norm,
    layout_geometry,
    upscale_ratio,
)
from videoflow.application.short_composition.plan import (
    camera_size,
    is_protected,
    overlapping_scenes,
)
from videoflow.application.short_composition.tracking import scene_crop_samples, static_crop
from videoflow.domain.scenes import ScenesManifest
from videoflow.domain.short_composition import ShortCompositionPlan


def validate_plan(
    plan: ShortCompositionPlan,
    manifest: ScenesManifest,
    *,
    broll_exists: Callable[[Path], bool] | None = None,
) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    if (plan.target_width, plan.target_height) != (CANVAS_WIDTH, CANVAS_HEIGHT):
        errors.append("canvas must be exactly 1080x1920")
    cam_w, cam_h = camera_size(manifest)
    scenes = sorted(manifest.scenes, key=lambda item: item.start_sample)
    for segment in plan.segments:
        start = plan.start + segment.rel_start
        end = plan.start + segment.rel_end
        if end - start < 2.5 - 1e-6:
            errors.append(f"{segment.seg_id}: segment shorter than 2.5s")
        touched = overlapping_scenes(scenes, start, end)
        if segment.layout == "SPLIT_BROLL":
            if any(is_protected(scene) for scene in touched):
                errors.append(f"{segment.seg_id}: B-roll overlaps a protected scene")
            exists = None
            source = segment.broll_source
            if broll_exists is not None and source is not None and source.path:
                exists = broll_exists(Path(source.path).expanduser())
            check = validate_broll(source, is_file=exists)
            if not check.ok:
                errors.append(f"{segment.seg_id}: {check.reason}")
        if not captions_are_safe(segment.layout):
            errors.append(f"{segment.seg_id}: captions collide with a Shorts safe zone")
        samples = scene_crop_samples(
            [
                {"start_sec": scene.start_sec, "face_bbox_norm": scene.face_bbox_norm}
                for scene in touched
            ],
            cam_w=cam_w,
            cam_h=cam_h,
            layout=segment.layout,
            zoom=segment.face_zoom,
        )
        crop = static_crop(samples)
        if crop is not None:
            geometry = layout_geometry(segment.layout)
            ratio = upscale_ratio(crop.width, geometry.face.width)
            if ratio > MAX_FACE_UPSCALE:
                message = (
                    f"{segment.seg_id}: PIP_LOW_RES_WARNING ({ratio:.2f}x upscale)"
                )
                if segment.layout.startswith("SPLIT_SCREEN"):
                    errors.append(message)
                else:
                    warnings.append(message)
        # Face anchor sanity: the crop must keep the median face center inside.
        face = next(
            (
                face_box_from_norm(scene.face_bbox_norm.model_dump())
                for scene in touched
                if scene.face_bbox_norm is not None
            ),
            None,
        )
        if face is not None and crop is not None:
            face_x = face.cx * cam_w
            if not (crop.x <= face_x <= crop.right):
                warnings.append(f"{segment.seg_id}: face center is outside the crop")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "segment_count": len(plan.segments),
        "duration_sec": round(plan.duration_sec, 3),
    }


__all__ = ["validate_plan"]
