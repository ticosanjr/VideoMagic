"""Deterministic scene layouts and editing hints.

The rules live in the portable ``scene_rules`` package so the GPU worker and
the local pipeline cannot drift.
"""

from __future__ import annotations

from scene_rules import (
    LONG_STATIC_SEC,
    LOW_SHARPNESS,
    PROTECTED_LAYOUTS,
    SCREEN_ACTIVITY_EDGE_DENSITY,
    protected_from_broll,
)
from scene_rules import (
    editing_hints as _editing_hints,
)


def editing_hints(
    *,
    layout: str,
    duration_sec: float,
    edge_density: float,
    sharpness_laplacian: float,
    previous_layout: str | None,
) -> list[str]:
    return _editing_hints(
        layout=layout,
        duration_sec=duration_sec,
        edge_density=edge_density,
        sharpness_laplacian=sharpness_laplacian,
        previous_layout=previous_layout,
    )


__all__ = [
    "LONG_STATIC_SEC",
    "LOW_SHARPNESS",
    "PROTECTED_LAYOUTS",
    "SCREEN_ACTIVITY_EDGE_DENSITY",
    "editing_hints",
    "protected_from_broll",
]
