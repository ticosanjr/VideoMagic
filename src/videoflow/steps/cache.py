"""Small JSON cache for expensive analysis steps.

The cache key is a hash of the source PCM digest plus the step parameters and a
cache schema version. Entries are content-addressed and stored outside the
project, so different output directories can reuse the same VAD/transcript.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from videoflow.runtime import portable_home

CACHE_VERSION = 1


def cache_enabled() -> bool:
    return os.environ.get("VIDEOWFLOW_RECIPE_CACHE", "1") != "0"


def cache_dir() -> Path:
    return portable_home() / "cache" / f"recipe-v{CACHE_VERSION}"


def cache_key(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def cache_get(kind: str, key: str) -> dict[str, Any] | None:
    if not cache_enabled():
        return None
    path = cache_dir() / kind / f"{key}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("v") != CACHE_VERSION:
        return None
    return payload


def cache_put(kind: str, key: str, payload: dict[str, Any]) -> Path | None:
    if not cache_enabled():
        return None
    directory = cache_dir() / kind
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{key}.json"
        temporary = target.with_suffix(".json.tmp")
        data = {"v": CACHE_VERSION, **payload}
        temporary.write_text(
            json.dumps(data, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
    except OSError:
        return None
    return target


def prune_cache(
    *,
    max_age_days: int = 30,
    max_bytes: int = 512 * 1024 * 1024,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Trim the global analysis cache by age and size."""

    directory = cache_dir()
    if not directory.is_dir():
        return {"ok": True, "removed": [], "freed_bytes": 0, "kept_bytes": 0}
    cutoff = time.time() - max(1, max_age_days) * 86400
    files: list[tuple[float, int, Path]] = []
    for path in directory.rglob("*.json"):
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append((stat.st_mtime, stat.st_size, path))
    files.sort(key=lambda item: item[0], reverse=True)
    kept = 0
    removed: list[str] = []
    freed = 0
    for mtime, size, path in files:
        stale = mtime < cutoff
        over = kept + size > max(1, max_bytes)
        if stale or over:
            removed.append(str(path))
            freed += size
            if not dry_run:
                with suppress(OSError):
                    path.unlink()
        else:
            kept += size
    return {
        "ok": True,
        "removed": removed,
        "freed_bytes": freed,
        "kept_bytes": kept,
        "dry_run": dry_run,
    }


def clear_cache() -> int:
    """Remove cached analysis entries. Returns the number of files removed."""

    removed = 0
    directory = cache_dir()
    if not directory.is_dir():
        return 0
    for path in directory.rglob("*.json"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed
