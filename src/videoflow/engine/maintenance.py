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
