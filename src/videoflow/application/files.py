"""Small filesystem helpers shared by background workers."""

from __future__ import annotations

from pathlib import Path


def stat_signature(path: Path) -> list[int] | None:
    if not path.is_file():
        return None
    stat = path.stat()
    return [stat.st_mtime_ns, stat.st_size]
