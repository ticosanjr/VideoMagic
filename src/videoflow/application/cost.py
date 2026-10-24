"""Token accounting for OpenAI-compatible calls."""

from __future__ import annotations

import threading
from typing import Any

_LOCK = threading.Lock()
_TOTALS: dict[str, Any] = {
    "calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "by_model": {},
}


def record_usage(model: str, usage: dict[str, Any] | None) -> None:
    if not isinstance(usage, dict):
        return
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    with _LOCK:
        _TOTALS["calls"] += 1
        _TOTALS["prompt_tokens"] += prompt
        _TOTALS["completion_tokens"] += completion
        entry = _TOTALS["by_model"].setdefault(
            model or "unknown", {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        )
        entry["calls"] += 1
        entry["prompt_tokens"] += prompt
        entry["completion_tokens"] += completion


def snapshot() -> dict[str, Any]:
    with _LOCK:
        return {
            "calls": _TOTALS["calls"],
            "prompt_tokens": _TOTALS["prompt_tokens"],
            "completion_tokens": _TOTALS["completion_tokens"],
            "by_model": {key: dict(value) for key, value in _TOTALS["by_model"].items()},
        }


def reset() -> None:
    with _LOCK:
        _TOTALS["calls"] = 0
        _TOTALS["prompt_tokens"] = 0
        _TOTALS["completion_tokens"] = 0
        _TOTALS["by_model"].clear()
