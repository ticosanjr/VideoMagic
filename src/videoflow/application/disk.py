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


def prune_render_segments(output: Path | str) -> list[Path]:
    """Remove disposable segment caches after a validated delivery."""

    root = Path(output).expanduser()
    removed: list[Path] = []
    for relative in ("render/segments", "work/segments"):
        target = root / relative
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            removed.append(target)
    return removed


__all__ = [
    "DEFAULT_MIN_FREE_GB",
    "ensure_free_space",
    "free_gb",
    "prune_render_segments",
]
