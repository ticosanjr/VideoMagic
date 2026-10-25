"""Per-provider circuit breaker for LLM calls."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from videoflow.domain.errors import LlmError

_LOCK = threading.Lock()
_STATE: dict[str, dict[str, float]] = {}


def _key(base_url: str) -> str:
    return base_url.rstrip("/")


def _threshold() -> int:
    return max(1, int(os.environ.get("VIDEOWFLOW_CIRCUIT_FAILURES", "3") or 3))


def _cooldown() -> float:
    return max(1.0, float(os.environ.get("VIDEOWFLOW_CIRCUIT_COOLDOWN", "30") or 30))


def allow(base_url: str) -> bool:
    with _LOCK:
        state = _STATE.get(_key(base_url))
        if state is None:
            return True
        open_until = state.get("open_until", 0.0)
        if open_until == 0.0:
            return True
        if open_until <= time.monotonic():
            _STATE.pop(_key(base_url), None)
            return True
        return False


def failure(base_url: str) -> None:
    with _LOCK:
        key = _key(base_url)
        state = _STATE.setdefault(key, {"failures": 0.0, "open_until": 0.0})
        state["failures"] = state.get("failures", 0.0) + 1
        if state["failures"] >= _threshold():
            state["open_until"] = time.monotonic() + _cooldown()


def success(base_url: str) -> None:
    with _LOCK:
        _STATE.pop(_key(base_url), None)


def reset() -> None:
    with _LOCK:
        _STATE.clear()


class CircuitBreakerLlm:
    def __init__(self, client: Any, base_url: str) -> None:
        self.client = client
        self.base_url = base_url

    def complete_json(self, prompt: str, schema_name: str) -> dict[str, Any]:
        if not allow(self.base_url):
            raise LlmError(
                f"Provider {self.base_url} is cooling down after repeated failures"
            )
        try:
            result = self.client.complete_json(prompt, schema_name)
        except LlmError:
            failure(self.base_url)
            raise
        success(self.base_url)
        return result
