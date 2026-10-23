"""Persistent recipe run history, stored beside the project artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

MAX_RUNS = 30


def history_path(output: Path) -> Path:
    return Path(output) / "work" / "run-history.json"


def append_run(output: Path, record: dict[str, Any], *, limit: int = MAX_RUNS) -> Path:
    path = history_path(output)
    runs = read_runs(output)
    runs = [item for item in runs if item.get("job_id") != record.get("job_id")]
    runs.append(record)
    runs = runs[-limit:]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"runs": runs}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def read_runs(
    output: Path,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    path = history_path(output)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    runs = payload.get("runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        return []
    items = [item for item in runs if isinstance(item, dict)]
    start = max(0, int(offset))
    if limit is None:
        return items[start:]
    return items[start : start + max(0, int(limit))]
