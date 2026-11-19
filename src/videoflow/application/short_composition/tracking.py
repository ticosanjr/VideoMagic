"""Scene-median crops and optional smoothed tracking."""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from videoflow.application.short_composition.geometry import (
    CropBox,
    FaceBox,
    crop_for_panel,
    face_box_from_norm,
    layout_geometry,
)


@dataclass(frozen=True, slots=True)
class CropSample:
    time_sec: float
    crop: CropBox
    face: FaceBox | None = None


def median_face(faces: list[FaceBox | None]) -> FaceBox | None:
    present = [item for item in faces if item is not None]
    if not present:
        return None
    return FaceBox(
        cx=statistics.median(item.cx for item in present),
        cy=statistics.median(item.cy for item in present),
        w=statistics.median(item.w for item in present),
        h=statistics.median(item.h for item in present),
    )


def face_centers(scenes: list[dict[str, object]]) -> list[float]:
    values: list[float] = []
    for scene in scenes:
        face = face_box_from_norm(scene.get("face_bbox_norm"))  # type: ignore[arg-type]
        if face is not None:
            values.append(face.cx)
    return values


def needs_smoothing(values: list[float], *, threshold: float = 0.08) -> bool:
    if len(values) < 3:
        return False
    mean = statistics.fmean(values)
    if mean <= 0:
        return False
    return statistics.pstdev(values) / mean > threshold


def smooth_series(
    values: list[float],
    *,
    deadzone_px: float,
    alpha: float = 0.08,
) -> list[float]:
    """EMA with a deadzone so micro-jitter does not move the crop."""

    if not values:
        return []
    factor = max(0.01, min(1.0, float(alpha)))
    zone = max(0.0, float(deadzone_px))
    result = [float(values[0])]
    current = result[0]
    for value in values[1:]:
        incoming = float(value)
        if abs(incoming - current) < zone:
            result.append(current)
            continue
        current = factor * incoming + (1.0 - factor) * current
        result.append(current)
    return result


def clamp_crop_position(crop: CropBox, cam_w: int, cam_h: int) -> CropBox:
    x = max(0, min(max(0, cam_w - crop.width), crop.x))
    y = max(0, min(max(0, cam_h - crop.height), crop.y))
    return CropBox(x=x, y=y, width=crop.width, height=crop.height)


def scene_crop_samples(
    scenes: list[dict[str, object]],
    *,
    cam_w: int,
    cam_h: int,
    layout: str,
    zoom: float = 1.0,
    smooth: bool = False,
    deadzone: float = 0.05,
    alpha: float = 0.08,
) -> list[CropSample]:
    """Compute one crop per scene and optionally smooth x/y between scenes."""

    geometry = layout_geometry(layout)
    samples: list[CropSample] = []
    for scene in scenes:
        face = face_box_from_norm(scene.get("face_bbox_norm"))  # type: ignore[arg-type]
        crop = crop_for_panel(
            cam_w=cam_w,
            cam_h=cam_h,
            panel=geometry.face,
            face=face,
            zoom=zoom,
        )
        try:
            time_sec = float(scene.get("start_sec", 0.0))
        except (TypeError, ValueError):
            time_sec = 0.0
        samples.append(CropSample(time_sec=time_sec, crop=crop, face=face))
    if not smooth or len(samples) < 2:
        return samples
    centers = face_centers(scenes)
    if not needs_smoothing(centers):
        return samples
    xs = smooth_series(
        [float(sample.crop.x) for sample in samples],
        deadzone_px=deadzone * samples[0].crop.width,
        alpha=alpha,
    )
    ys = smooth_series(
        [float(sample.crop.y) for sample in samples],
        deadzone_px=deadzone * samples[0].crop.height,
        alpha=alpha,
    )
    smoothed: list[CropSample] = []
    for sample, x, y in zip(samples, xs, ys, strict=False):
        crop = clamp_crop_position(
            CropBox(x=round(x), y=round(y), width=sample.crop.width, height=sample.crop.height),
            cam_w,
            cam_h,
        )
        smoothed.append(CropSample(time_sec=sample.time_sec, crop=crop, face=sample.face))
    return smoothed


def static_crop(samples: list[CropSample]) -> CropBox | None:
    """One scene-median crop for a whole segment."""

    if not samples:
        return None
    return CropBox(
        x=round(statistics.median(sample.crop.x for sample in samples)),
        y=round(statistics.median(sample.crop.y for sample in samples)),
        width=round(statistics.median(sample.crop.width for sample in samples)),
        height=round(statistics.median(sample.crop.height for sample in samples)),
    )


__all__ = [
    "CropSample",
    "clamp_crop_position",
    "face_centers",
    "median_face",
    "needs_smoothing",
    "scene_crop_samples",
    "smooth_series",
    "static_crop",
]
