"""Deterministic scene layouts and editing hints."""

from __future__ import annotations

PROTECTED_LAYOUTS = {
    "SCREEN_SHARE_PIP",
    "SCREEN_SHARE_FULL",
    "DUAL_CANVAS_OBS",
}
SCREEN_ACTIVITY_EDGE_DENSITY = 0.05
LONG_STATIC_SEC = 12.0
LOW_SHARPNESS = 60.0


def editing_hints(
    *,
    layout: str,
    duration_sec: float,
    edge_density: float,
    sharpness_laplacian: float,
    previous_layout: str | None,
) -> list[str]:
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
    "editing_hints",
    "protected_from_broll",
]
