"""Pure scene rules shared by local and worker scene pipelines."""

from __future__ import annotations

import statistics

PROTECTED_LAYOUTS = frozenset(
    {"SCREEN_SHARE_PIP", "SCREEN_SHARE_FULL", "DUAL_CANVAS_OBS"}
)
SCREEN_ACTIVITY_EDGE_DENSITY = 0.05
LONG_STATIC_SEC = 12.0
LOW_SHARPNESS = 60.0
TALKING_HEAD_FACE_AREA = 0.055
SCREEN_SHARE_EDGE_DENSITY = 0.08


def median(values: list[float], default: float = 0.0) -> float:
    """Return a rounded median, or ``default`` for an empty sample."""

    return round(statistics.median(values), 6) if values else default


def sample_times(
    start: float,
    end: float,
    *,
    max_frames: int = 20,
    interval: float = 0.5,
) -> list[float]:
    """Pick deterministic sample timestamps inside a scene span."""

    duration = max(0.0, float(end) - float(start))
    if duration <= 0:
        return [float(start)]
    count = max(3, min(max(3, int(max_frames)), int(duration / max(0.1, interval)) + 1))
    return [
        min(float(end) - 1e-4, float(start) + duration * (index + 0.5) / count)
        for index in range(count)
    ]


def classify_layout(
    *,
    face_count: int,
    face_area_ratio: float,
    edge_density: float,
    width: int,
    height: int,
    topology: str,
) -> str:
    """Classify one scene from aggregate visual statistics."""

    if topology == "dual_canvas" or (width == 3840 and height == 1080):
        return "DUAL_CANVAS_OBS"
    if face_count >= 1 and face_area_ratio >= TALKING_HEAD_FACE_AREA:
        return "TALKING_HEAD"
    if face_count >= 1:
        return "SCREEN_SHARE_PIP"
    if edge_density >= SCREEN_SHARE_EDGE_DENSITY:
        return "SCREEN_SHARE_FULL"
    return "BROLL_OR_FOOTAGE"


def editing_hints(
    *,
    layout: str,
    duration_sec: float,
    edge_density: float,
    sharpness_laplacian: float,
    previous_layout: str | None,
) -> list[str]:
    """Deterministic editing hints for one classified scene."""

    hints: list[str] = []
    if layout == "TALKING_HEAD" and duration_sec >= LONG_STATIC_SEC:
        hints.append("LONG_STATIC_SHOT")
    if previous_layout is not None and layout != previous_layout:
        hints.append("SCENE_TYPE_SWITCH")
    if layout in PROTECTED_LAYOUTS and edge_density >= SCREEN_ACTIVITY_EDGE_DENSITY:
        hints.append("PROTECT_FROM_BROLL")
    if layout == "TALKING_HEAD" and sharpness_laplacian < LOW_SHARPNESS:
        hints.append("LOW_SHARPNESS_WARNING")
    if layout == "TALKING_HEAD" and "PROTECT_FROM_BROLL" not in hints:
        hints.append("SAFE_FOR_BROLL")
    if layout == "DUAL_CANVAS_OBS":
        hints.append("DUAL_CANVAS_READY")
    return hints


def protected_from_broll(layout: str, hints: list[str]) -> bool:
    if layout in PROTECTED_LAYOUTS:
        return True
    return "PROTECT_FROM_BROLL" in hints


__all__ = [
    "LONG_STATIC_SEC",
    "LOW_SHARPNESS",
    "PROTECTED_LAYOUTS",
    "SCREEN_ACTIVITY_EDGE_DENSITY",
    "SCREEN_SHARE_EDGE_DENSITY",
    "TALKING_HEAD_FACE_AREA",
    "classify_layout",
    "editing_hints",
    "median",
    "protected_from_broll",
    "sample_times",
]
