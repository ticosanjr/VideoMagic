from __future__ import annotations

import time
from types import SimpleNamespace

import httpx
import pytest

from videoflow.application import circuit, cost
from videoflow.application.intelligence.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from videoflow.application.intelligence.providers.opencode_v2 import (
    OpenCodeV2Provider,
)
from videoflow.application.intelligence.router import Intelligence
from videoflow.application.settings import AppSettings, IntelligenceSettings
from videoflow.domain.errors import LlmError


def _provider(**kwargs) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        provider_id="test",
        base_url="http://worker.test/v1",
        model="gpt-4o",
        retries=0,
        **kwargs,
    )


def test_budget_is_checked_before_any_http_call(monkeypatch) -> None:
    cost.reset()
    circuit.reset()
    monkeypatch.setenv("VIDEOWFLOW_COST_BUDGET_USD", "0.01")
    cost.record_usage("gpt-4o", {"prompt_tokens": 1_000_000, "completion_tokens": 0})
    provider = _provider()
    monkeypatch.setattr(
        provider,
        "_post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("HTTP must not be called when budget is exhausted")
        ),
    )
    with pytest.raises(LlmError, match="budget exceeded"):
        provider.complete_json("hello", "schema")
    cost.reset()
    monkeypatch.delenv("VIDEOWFLOW_COST_BUDGET_USD", raising=False)


def test_circuit_breaker_blocks_the_second_call(monkeypatch) -> None:
    circuit.reset()
    monkeypatch.setenv("VIDEOWFLOW_CIRCUIT_FAILURES", "1")
    monkeypatch.setenv("VIDEOWFLOW_CIRCUIT_COOLDOWN", "60")
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, text="down")

    provider = _provider(transport=httpx.MockTransport(handler))
    with pytest.raises(LlmError, match="HTTP 500"):
        provider.complete_json("hello", "schema")
    with pytest.raises(LlmError, match="cooling down"):
        provider.complete_json("hello", "schema")
    assert calls == 1
    circuit.reset()
    monkeypatch.delenv("VIDEOWFLOW_CIRCUIT_FAILURES", raising=False)
    monkeypatch.delenv("VIDEOWFLOW_CIRCUIT_COOLDOWN", raising=False)


def test_opencode_status_is_cached_for_30_seconds() -> None:
    provider = OpenCodeV2Provider(base_url="http://127.0.0.1:4096")
    calls = 0

    def healthy(*args, **kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(status_code=200)

    provider._request = healthy
    started = time.perf_counter()
    assert provider.status().ready is True
    assert provider.status().ready is True
    assert time.perf_counter() - started < 0.1
    assert calls == 1

    def down(*args, **kwargs):
        raise LlmError("down")

    provider._request = down
    assert provider.status().ready is True
    assert calls == 1


def _settings(allow_network: bool) -> AppSettings:
    return AppSettings(
        intelligence=IntelligenceSettings(
            allow_network=allow_network,
            opencode_base_url="",
            deepseek_base_url="https://api.deepseek.com",
        )
    )


def test_deepseek_is_not_registered_without_key_or_network(monkeypatch) -> None:
    monkeypatch.setattr(
        "videoflow.application.intelligence.router.list_providers", lambda: []
    )
    monkeypatch.setattr(
        "videoflow.application.intelligence.router.get_secret", lambda name: ""
    )
    providers = Intelligence(_settings(False))._build_providers()
    assert "deepseek" not in providers

    monkeypatch.setattr(
        "videoflow.application.intelligence.router.get_secret",
        lambda name: "key" if name == "DEEPSEEK_API_KEY" else "",
    )
    assert "deepseek" not in Intelligence(_settings(False))._build_providers()
    assert "deepseek" in Intelligence(_settings(True))._build_providers()

    # A configured local OpenCode provider must not imply network permission.
    monkeypatch.setattr(
        "videoflow.application.intelligence.router.list_providers",
        lambda: [
            {
                "id": "opencode_v2",
                "kind": "opencode_v2",
                "capability": "llm",
                "base_url": "http://127.0.0.1:4096",
                "model": "local",
            }
        ],
    )
    providers = Intelligence(_settings(False))._build_providers()
    assert "opencode_v2" in providers
    assert "deepseek" not in providers
