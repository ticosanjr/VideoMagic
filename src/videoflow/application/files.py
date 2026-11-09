"""Small filesystem helpers shared by background workers."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


def stat_signature(path: Path) -> list[int] | None:
    if not path.is_file():
        return None
    stat = path.stat()
    return [stat.st_mtime_ns, stat.st_size]


def read_json_dict(path: Path) -> dict[str, Any]:
    """Read a JSON object, returning an empty dict for missing or invalid files."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON object through a per-thread temporary file and replace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{threading.get_ident()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
