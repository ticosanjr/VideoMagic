"""B-roll normalization and safe fallbacks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from videoflow.application.short_composition.geometry import CANVAS_WIDTH, LayoutGeometry
from videoflow.domain.short_composition import BrollSource, ShortSegment


@dataclass(frozen=True, slots=True)
class BrollCheck:
    ok: bool
    path: Path | None = None
    reason: str = ""


def validate_broll(
    source: BrollSource | None,
    *,
    is_file: bool | None = None,
) -> BrollCheck:
    if source is None:
        return BrollCheck(ok=False, reason="missing broll_source")
    if source.type == "stock":
        if source.fallback_query.strip():
            return BrollCheck(ok=True, reason="stock query")
        return BrollCheck(ok=False, reason="stock query is empty")
    raw = source.path.strip()
    if not raw:
        return BrollCheck(ok=False, reason="broll path is empty")
    path = Path(raw).expanduser()
    exists = path.is_file() if is_file is None else bool(is_file)
    if not exists:
        return BrollCheck(ok=False, path=path, reason=f"broll file is missing: {path}")
    if path.suffix.casefold() not in {".mp4", ".mov", ".m4v", ".webm", ".mkv"}:
        return BrollCheck(ok=False, path=path, reason="broll file is not a video")
    return BrollCheck(ok=True, path=path, reason="")


def normalize_filter(
    *,
    width: int,
    height: int,
    fps: int,
) -> str:
    """FFmpeg filter chain for one B-roll panel; setpts comes from the input."""

    target_w = max(2, int(width))
    target_h = max(2, int(height))
    return (
        f"fps={max(1, int(fps))},"
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={target_w}:{target_h},setsar=1,format=yuv420p"
    )


def input_args(*, loop: bool) -> list[str]:
    return ["-stream_loop", "-1"] if loop else []


def broll_panel(geometry: LayoutGeometry) -> tuple[int, int]:
    if geometry.broll is None:
        return (CANVAS_WIDTH, CANVAS_WIDTH)
    return (geometry.broll.width, geometry.broll.height)


def broll_fallback(segment: ShortSegment) -> ShortSegment:
    """Never abort the whole Short because one B-roll asset is unusable."""

    return segment.model_copy(
        update={
            "layout": "FULL_FACE",
            "broll_source": None,
            "face_zoom": 1.12,
        }
    )


__all__ = [
    "BrollCheck",
    "broll_fallback",
    "broll_panel",
    "input_args",
    "normalize_filter",
    "validate_broll",
]
