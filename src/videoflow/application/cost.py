"""Token accounting for OpenAI-compatible calls."""

from __future__ import annotations

import threading
from typing import Any

# USD per one million tokens. Unknown models report 0 instead of guessing.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.4, 1.6),
    "o4-mini": (1.1, 4.4),
}

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


def budget_usd() -> float:
    import os

    try:
        return max(0.0, float(os.environ.get("VIDEOWFLOW_COST_BUDGET_USD", "0") or 0))
    except ValueError:
        return 0.0


def ensure_within_budget() -> None:
    from videoflow.domain.errors import LlmError

    budget = budget_usd()
    if budget <= 0:
        return
    used = snapshot()["estimated_cost_usd"]
    if used >= budget:
        raise LlmError(
            f"LLM budget exceeded: ${used:.4f} of ${budget:.2f}. "
            "Raise VIDEOWFLOW_COST_BUDGET_USD or reset usage."
        )


def estimate_cost(model: str, prompt: int, completion: int) -> float:
    price = PRICES.get(model)
    if price is None:
        return 0.0
    input_price, output_price = price
    return round(
        (prompt / 1_000_000) * input_price + (completion / 1_000_000) * output_price,
        6,
    )


def snapshot() -> dict[str, Any]:
    with _LOCK:
        by_model = {}
        total_cost = 0.0
        for key, value in _TOTALS["by_model"].items():
            entry = dict(value)
            entry["estimated_cost_usd"] = estimate_cost(
                key, entry["prompt_tokens"], entry["completion_tokens"]
            )
            total_cost += entry["estimated_cost_usd"]
            by_model[key] = entry
        budget = budget_usd()
        return {
            "calls": _TOTALS["calls"],
            "prompt_tokens": _TOTALS["prompt_tokens"],
            "completion_tokens": _TOTALS["completion_tokens"],
            "estimated_cost_usd": round(total_cost, 6),
            "budget_usd": budget,
            "remaining_usd": round(max(0.0, budget - total_cost), 6) if budget else None,
            "by_model": by_model,
        }


def reset() -> None:
    with _LOCK:
        _TOTALS["calls"] = 0
        _TOTALS["prompt_tokens"] = 0
        _TOTALS["completion_tokens"] = 0
        _TOTALS["by_model"].clear()
