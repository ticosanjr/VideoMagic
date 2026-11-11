"""Per-task intelligence telemetry and budget accounting."""

from __future__ import annotations

import threading
from typing import Any

from videoflow.application.cost import budget_usd, estimate_cost

_LOCK = threading.Lock()
_TOTALS: dict[str, Any] = {
    "calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "estimated_cost_usd": 0.0,
    "by_task": {},
    "by_provider": {},
}


def record(
    *,
    task: str,
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = 0,
    cost_usd: float | None = None,
    fallback: str = "none",
    error: str = "",
) -> None:
    cost = (
        float(cost_usd)
        if cost_usd is not None
        else estimate_cost(model, prompt_tokens, completion_tokens)
    )
    with _LOCK:
        _TOTALS["calls"] += 1
        _TOTALS["prompt_tokens"] += prompt_tokens
        _TOTALS["completion_tokens"] += completion_tokens
        _TOTALS["estimated_cost_usd"] += cost
        task_entry = _TOTALS["by_task"].setdefault(
            task or "generic",
            {
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "estimated_cost_usd": 0.0,
                "latency_ms": 0,
                "fallbacks": 0,
                "errors": 0,
            },
        )
        task_entry["calls"] += 1
        task_entry["prompt_tokens"] += prompt_tokens
        task_entry["completion_tokens"] += completion_tokens
        task_entry["estimated_cost_usd"] = round(
            task_entry["estimated_cost_usd"] + cost, 6
        )
        task_entry["latency_ms"] += latency_ms
        if fallback != "none":
            task_entry["fallbacks"] += 1
        if error:
            task_entry["errors"] += 1
        provider_entry = _TOTALS["by_provider"].setdefault(
            provider or "unknown",
            {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0},
        )
        provider_entry["calls"] += 1
        provider_entry["prompt_tokens"] += prompt_tokens
        provider_entry["completion_tokens"] += completion_tokens
        provider_entry["cost_usd"] = round(provider_entry["cost_usd"] + cost, 6)


def snapshot() -> dict[str, Any]:
    with _LOCK:
        return {
            "calls": _TOTALS["calls"],
            "prompt_tokens": _TOTALS["prompt_tokens"],
            "completion_tokens": _TOTALS["completion_tokens"],
            "estimated_cost_usd": round(_TOTALS["estimated_cost_usd"], 6),
            "budget_usd": budget_usd(),
            "by_task": {
                key: dict(value) for key, value in _TOTALS["by_task"].items()
            },
            "by_provider": {
                key: dict(value) for key, value in _TOTALS["by_provider"].items()
            },
        }


def reset() -> None:
    with _LOCK:
        _TOTALS["calls"] = 0
        _TOTALS["prompt_tokens"] = 0
        _TOTALS["completion_tokens"] = 0
        _TOTALS["estimated_cost_usd"] = 0.0
        _TOTALS["by_task"].clear()
        _TOTALS["by_provider"].clear()
