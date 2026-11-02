"""Output-local checkpoint and cache pruning."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from videoflow.engine.history import MAX_RUNS, history_path, read_runs


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def _prune_old_entries(
    directory: Path,
    cutoff: float,
    *,
    kind: str,
    removed: list[dict[str, Any]],
    dry_run: bool,
) -> int:
    freed = 0
    if not directory.is_dir():
        return freed
    for item in directory.iterdir():
        try:
            if item.stat().st_mtime >= cutoff:
                continue
        except OSError:
            continue
        size = _size(item)
        removed.append({"kind": kind, "path": str(item), "bytes": size})
        freed += size
        if not dry_run:
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
    return freed


def prune_output(
    output: Path,
    *,
    keep_days: int = 14,
    keep_steps: int = 200,
    keep_runs: int = MAX_RUNS,
    dry_run: bool = False,
) -> dict[str, Any]:
    output = Path(output).expanduser()
    cutoff = time.time() - max(1, keep_days) * 86400
    removed: list[dict[str, Any]] = []
    freed = 0
    steps_dir = output / "work" / "steps"
    if steps_dir.is_dir():
        directories = sorted(
            (item for item in steps_dir.iterdir() if item.is_dir()),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for index, directory in enumerate(directories):
            if index < max(1, keep_steps):
                continue
            size = _size(directory)
            removed.append({"kind": "checkpoint", "path": str(directory), "bytes": size})
            freed += size
            if not dry_run:
                shutil.rmtree(directory, ignore_errors=True)
    broll_dir = output / "broll-cache"
    if broll_dir.is_dir():
        for item in broll_dir.iterdir():
            try:
                if item.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue
            size = _size(item)
            removed.append({"kind": "broll", "path": str(item), "bytes": size})
            freed += size
            if not dry_run:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
    for kind, directory in (
        ("preview-frame", output / "preview" / "frames"),
        ("render-segment", output / "render" / "segments"),
    ):
        freed += _prune_old_entries(
            directory,
            cutoff,
            kind=kind,
            removed=removed,
            dry_run=dry_run,
        )
    legacy_preview = output / "preview" / "timeline-preview.mp4"
    if legacy_preview.is_file():
        size = legacy_preview.stat().st_size
        removed.append(
            {"kind": "preview-intermediate", "path": str(legacy_preview), "bytes": size}
        )
        freed += size
        if not dry_run:
            legacy_preview.unlink(missing_ok=True)
    for directory in (output / "preview", output / "render"):
        if not directory.is_dir():
            continue
        for partial in directory.iterdir():
            if not partial.name.endswith(".part.mp4"):
                continue
            try:
                if partial.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue
            size = partial.stat().st_size
            removed.append({"kind": "partial", "path": str(partial), "bytes": size})
            freed += size
            if not dry_run:
                partial.unlink(missing_ok=True)
    runs = read_runs(output)
    trimmed = 0
    if len(runs) > keep_runs:
        trimmed = len(runs) - keep_runs
        if not dry_run:
            import json

            path = history_path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"runs": runs[-keep_runs:]}, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    return {
        "ok": True,
        "output": str(output),
        "dry_run": dry_run,
        "removed": removed,
        "freed_bytes": freed,
        "trimmed_runs": trimmed,
        "kept_steps": min(keep_steps, len(list(steps_dir.iterdir()))) if steps_dir.is_dir() else 0,
    }
