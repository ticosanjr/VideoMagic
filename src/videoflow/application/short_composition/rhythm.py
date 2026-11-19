"""Layout snapping, SFX cues, and Short ending."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from videoflow.domain.short_composition import ShortCompositionPlan

DEFAULT_PAD_MS = 350
DEFAULT_FADE_MS = 80
DEFAULT_SFX = "whoosh_soft.wav"
DEFAULT_SFX_DB = -18.0


def snap_boundaries(
    plan: ShortCompositionPlan,
    candidates: Iterable[float],
    *,
    tolerance: float = 0.3,
    min_duration: float = 2.5,
) -> tuple[ShortCompositionPlan, list[str]]:
    """Move internal layout cuts to a nearby caption/ASU boundary."""

    if len(plan.segments) < 2:
        return plan, []
    points = sorted({round(float(value), 6) for value in candidates if value > 0})
    segments = [segment.model_copy() for segment in plan.segments]
    warnings: list[str] = []
    for index in range(len(segments) - 1):
        left = segments[index]
        right = segments[index + 1]
        boundary = left.rel_end
        candidates_here = [
            point
            for point in points
            if abs(point - boundary) <= max(0.0, tolerance) + 1e-9
        ]
        if not candidates_here:
            continue
        target = min(candidates_here, key=lambda point: abs(point - boundary))
        if abs(target - boundary) < 1e-6:
            continue
        if target - left.rel_start < min_duration - 1e-6:
            continue
        if right.rel_end - target < min_duration - 1e-6:
            continue
        segments[index] = left.model_copy(update={"rel_end": round(target, 6)})
        segments[index + 1] = right.model_copy(update={"rel_start": round(target, 6)})
        warnings.append(
            f"{left.seg_id}/{right.seg_id}: layout cut snapped "
            f"{boundary:.3f}s -> {target:.3f}s"
        )
    updated = plan.model_copy(update={"segments": segments})
    return updated, warnings


def layout_sfx_cues(
    plan: ShortCompositionPlan,
    *,
    enabled: bool = True,
    asset: str = DEFAULT_SFX,
    volume_db: float = DEFAULT_SFX_DB,
    lead_sec: float = 0.10,
) -> list[dict[str, object]]:
    if not enabled:
        return []
    cues: list[dict[str, object]] = []
    seen: set[float] = set()
    for previous, current in zip(plan.segments, plan.segments[1:], strict=False):
        if previous.layout == current.layout:
            continue
        time_sec = max(0.0, round(current.rel_start - max(0.0, lead_sec), 6))
        if time_sec in seen:
            continue
        seen.add(time_sec)
        cues.append(
            {
                "time_sec": time_sec,
                "asset": current.sfx_on_enter or asset,
                "volume_db": float(volume_db),
                "reason": "layout_change",
            }
        )
    return cues


def _nearest(values: Sequence[float], target: float, tolerance: float) -> float | None:
    if not values:
        return None
    nearest = min(values, key=lambda value: abs(value - target))
    return nearest if abs(nearest - target) <= tolerance else None


def end_settings(
    plan: ShortCompositionPlan,
    *,
    rms_valleys: Sequence[float] = (),
    next_speech_sec: float | None = None,
    pad_ms: int | None = None,
    fade_ms: int = DEFAULT_FADE_MS,
) -> dict[str, object]:
    """Add 350 ms and prefer the next speech edge or an RMS valley."""

    content_end = round(plan.duration_sec, 6)
    padding = max(0, int(plan.end_padding_ms if pad_ms is None else pad_ms))
    desired = content_end + padding / 1000.0
    snapped_to = "padding"
    effective = desired
    if next_speech_sec is not None:
        next_rel = float(next_speech_sec) - plan.start
        if content_end < next_rel < desired:
            effective = max(content_end, next_rel - 0.02)
            snapped_to = "next_speech"
    if snapped_to == "padding":
        valley = _nearest(
            [float(value) for value in rms_valleys],
            desired,
            tolerance=0.15,
        )
        if valley is not None and valley >= content_end:
            effective = valley
            snapped_to = "rms_valley"
    return {
        "content_end_sec": content_end,
        "effective_end_sec": round(effective, 6),
        "padding_ms": round((effective - content_end) * 1000.0, 3),
        "requested_padding_ms": padding,
        "fade_out_ms": max(0, int(fade_ms)),
        "snapped_to": snapped_to,
    }


__all__ = [
    "DEFAULT_FADE_MS",
    "DEFAULT_PAD_MS",
    "DEFAULT_SFX",
    "DEFAULT_SFX_DB",
    "end_settings",
    "layout_sfx_cues",
    "snap_boundaries",
]
