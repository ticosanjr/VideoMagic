"""Disk preflight and render-cache lifecycle helpers."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from videoflow.domain.errors import FilesystemError

DEFAULT_MIN_FREE_GB = 3.0


def free_gb(path: Path | str) -> float:
    probe = Path(path).expanduser()
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    return usage.free / (1024**3)


def ensure_free_space(path: Path | str, *, min_free_gb: float | None = None) -> float:
    minimum = DEFAULT_MIN_FREE_GB
    if min_free_gb is None:
        try:
            minimum = float(os.environ.get("VF_MIN_FREE_GB", "") or DEFAULT_MIN_FREE_GB)
        except ValueError:
            minimum = DEFAULT_MIN_FREE_GB
    else:
        minimum = float(min_free_gb)
    free = free_gb(path)
    if minimum > 0 and free < minimum:
        raise FilesystemError(
            f"Only {free:.1f} GB free at {path}; "
            f"{minimum:.1f} GB is required before rendering"
        )
    return free


def estimate_export_gb(state: object) -> float:
    """Estimate the working space for one export from duration and sources."""

    media = getattr(state, "media_info", None)
    if media is None or not getattr(media, "fps_den", 0):
        return 2.0
    fps = float(media.fps_num) / float(media.fps_den)
    duration_min = (
        float(media.duration_frames) / fps / 60.0 if fps > 0 else 0.0
    )
    source_bytes = 0
    for item in (getattr(state, "sources", {}) or {}).values():
        path = Path(getattr(item, "source_path", "")).expanduser()
        try:
            source_bytes += path.stat().st_size
        except OSError:
            continue
    estimate = max(2.0, duration_min * 0.25 + source_bytes / (1024**3) * 0.25)
    return round(estimate, 2)


def ensure_free_space_for_export(
    path: Path | str,
    state: object,
    *,
    extra_gb: float = 2.0,
) -> float:
    """Require estimated working space plus a safety margin."""

    required = estimate_export_gb(state) + max(0.0, float(extra_gb))
    free = free_gb(path)
    if free < required:
        raise FilesystemError(
            f"Only {free:.1f} GB free at {path}; "
            f"{required:.1f} GB is required for this export"
        )
    return free


def prune_render_segments(output: Path | str) -> list[Path]:
    """Remove disposable segment and alpha caches after a validated delivery."""

    root = Path(output).expanduser()
    removed: list[Path] = []
    for relative in (
        "render/segments",
        "work/segments",
        "exports/.alpha",
        "work/.alpha",
        ".alpha",
    ):
        target = root / relative
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            removed.append(target)
    return removed


__all__ = [
    "DEFAULT_MIN_FREE_GB",
    "ensure_free_space",
    "ensure_free_space_for_export",
    "estimate_export_gb",
    "free_gb",
    "prune_render_segments",
]
