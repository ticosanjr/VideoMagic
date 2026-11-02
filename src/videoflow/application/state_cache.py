"""Small read-only cache for parsed project state files.

Waveform and frame requests arrive in bursts for the same timeline. Parsing a
large ``project_state.json`` for every request is wasteful, so key the cache on
the file identity and mtime. Writes replace the state file atomically, which
changes the mtime and invalidates the entry.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

from videoflow.domain.state import ProjectState

MAX_ENTRIES = 4

_lock = threading.Lock()
_cache: OrderedDict[str, tuple[int, int, ProjectState]] = OrderedDict()


def load_state(path: Path) -> ProjectState:
    target = Path(path)
    stat = target.stat()
    key = str(target.resolve())
    with _lock:
        cached = _cache.get(key)
        if (
            cached is not None
            and cached[0] == stat.st_mtime_ns
            and cached[1] == stat.st_size
        ):
            _cache.move_to_end(key)
            return cached[2]
    state = ProjectState.model_validate_json(target.read_text(encoding="utf-8"))
    with _lock:
        _cache[key] = (stat.st_mtime_ns, stat.st_size, state)
        _cache.move_to_end(key)
        while len(_cache) > MAX_ENTRIES:
            _cache.popitem(last=False)
    return state


def clear_cache() -> None:
    with _lock:
        _cache.clear()
