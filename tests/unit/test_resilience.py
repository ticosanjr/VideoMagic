"""Provider circuit breaker and LLM budget."""

from __future__ import annotations

import pytest

from videoflow.application import circuit, cost
from videoflow.domain.errors import LlmError


class Flaky:
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, prompt: str, schema_name: str) -> dict[str, object]:
        self.calls += 1
        raise LlmError("offline")


def test_circuit_opens_after_repeated_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    circuit.reset()
    monkeypatch.setenv("VIDEOWFLOW_CIRCUIT_FAILURES", "2")
    monkeypatch.setenv("VIDEOWFLOW_CIRCUIT_COOLDOWN", "60")
    client = Flaky()
    wrapped = circuit.CircuitBreakerLlm(client, "http://offline.invalid/v1")

    for _ in range(2):
        with pytest.raises(LlmError):
            wrapped.complete_json("x", "y")

    with pytest.raises(LlmError, match="cooling down"):
        wrapped.complete_json("x", "y")
    assert client.calls == 2

    circuit.reset()


def test_circuit_recovers_after_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    circuit.reset()
    monkeypatch.setenv("VIDEOWFLOW_CIRCUIT_FAILURES", "1")
    monkeypatch.setenv("VIDEOWFLOW_CIRCUIT_COOLDOWN", "1")
    flaky = Flaky()
    wrapped = circuit.CircuitBreakerLlm(flaky, "http://offline.invalid/v1")
    with pytest.raises(LlmError):
        wrapped.complete_json("x", "y")
    assert circuit.allow("http://offline.invalid/v1") is False
    monkeypatch.setattr(circuit.time, "monotonic", lambda: 10**9)
    assert circuit.allow("http://offline.invalid/v1") is True
    circuit.reset()


def test_budget_blocks_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    cost.reset()
    monkeypatch.setenv("VIDEOWFLOW_COST_BUDGET_USD", "0.000001")
    cost.record_usage("gpt-4o", {"prompt_tokens": 1_000_000, "completion_tokens": 0})
    with pytest.raises(LlmError, match="budget exceeded"):
        cost.ensure_within_budget()
    cost.reset()
