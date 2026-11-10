"""Citation-friendly HTTP response cache."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from videoflow.runtime import portable_home


def cache_dir() -> Path:
    directory = portable_home() / "search-cache"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _cache_path(url: str) -> Path:
    return cache_dir() / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()[:24]}.json"


def _read_cache(url: str, ttl_hours: int) -> dict[str, Any] | None:
    try:
        payload = json.loads(_cache_path(url).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    fetched = float(payload.get("fetched_ts") or 0)
    if time.time() - fetched > ttl_hours * 3600:
        return None
    return payload


def _write_cache(url: str, payload: dict[str, Any]) -> None:
    target = _cache_path(url)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(target)
