"""HTTP helpers shared by worker routers."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

MAX_JOB_INPUTS = 64
PUBLIC_PATHS = frozenset({"/health"})

_SHA_CACHE: dict[tuple[str, int, int], str] = {}
_SHA_LOCK = threading.Lock()


def _sha256_cached(path: Path) -> str:
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    with _SHA_LOCK:
        cached = _SHA_CACHE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    with _SHA_LOCK:
        _SHA_CACHE[key] = value
    return value


def _parse_range(value: str, size: int) -> tuple[int, int] | None:
    text = str(value or "").strip()
    if not text.lower().startswith("bytes="):
        return None
    spec = text[6:].split(",", 1)[0].strip()
    if "-" not in spec:
        return None
    start_text, end_text = spec.split("-", 1)
    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
        else:
            suffix = int(end_text)
            if suffix <= 0:
                return None
            start = max(0, size - suffix)
            end = size - 1
    except ValueError:
        return None
    if start < 0 or end < start or start >= size:
        return None
    return start, min(end, size - 1)
