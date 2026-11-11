from __future__ import annotations

from typing import Any

import pytest

from videoflow.application.intelligence import (
    Intelligence,
    IntelligenceError,
    IntelligenceLlmAdapter,
    ProviderResult,
    build_intelligence,
    telemetry,
)
from videoflow.application.intelligence.providers.deepseek import DeepSeekProvider
from videoflow.application.intelligence.providers.opencode_v2 import (
    OpenCodeV2Provider,
)
from videoflow.application.intelligence.tasks import validate_score
from videoflow.application.settings import AppSettings
from videoflow.domain.errors import LlmError


class _Response:
    def __init__(self, status_code: int = 200, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


class _Client:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, str]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url))
        return self.handler(method, url, **kwargs)


def test_opencode_v2_health_models_and_text(monkeypatch) -> None:
    def handler(method: str, url: str, **kwargs):
        if url.endswith("/api/info"):
            return _Response(200, {"version": "2.0.0"})
        if "/api/model" in url:
            return _Response(
                200,
                {
                    "data": [
                        {
                            "id": "provider-a/model-a",
                            "modelID": "model-a",
                            "providerID": "provider-a",
                            "enabled": True,
                        }
                    ]
                },
            )
        if url.endswith("/api/experimental/generate/text"):
            assert kwargs["json"]["model"] == {
                "id": "model-a",
                "providerID": "provider-a",
            }
            return _Response(
                200,
                {
                    "data": {
                        "text": '{"score": 88, "arc": "hook", '
                        '"justification": "strong"}'
                    }
                },
            )
        return _Response(404)

    clients: list[_Client] = []

    def make_client(*args, **kwargs):
        client = _Client(handler)
        clients.append(client)
        return client

    monkeypatch.setattr(
        "videoflow.application.intelligence.providers.opencode_v2.httpx.Client",
        make_client,
    )
    provider = OpenCodeV2Provider(base_url="http://127.0.0.1:4096")
    assert provider.status().ready is True
    result = provider.complete_json("score this", "videoflow.short_score")
    assert result.data["score"] == 88
    assert result.provider == "opencode_v2"
    assert result.model == "provider-a/model-a"


def test_opencode_v2_status_reports_offline(monkeypatch) -> None:
    def make_client(*args, **kwargs):
        return _Client(lambda *a, **k: _Response(503))

    monkeypatch.setattr(
        "videoflow.application.intelligence.providers.opencode_v2.httpx.Client",
        make_client,
    )
    status = OpenCodeV2Provider(base_url="http://127.0.0.1:4096").status()
    assert status.ready is False
    assert "503" in status.detail


def test_deepseek_requires_a_key() -> None:
    assert DeepSeekProvider(api_key="").status().ready is False
    assert DeepSeekProvider(api_key="key").status().ready is True


class _FakeProvider:
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.id = name
        self.kind = name
        self.fail = fail

    def status(self):
        from videoflow.application.intelligence.models import IntelligenceStatus

        return IntelligenceStatus(
            provider=self.id, kind=self.kind, ready=True, detail="ready"
        )

    def complete_json(self, prompt, schema_name, **kwargs):
        if self.fail:
            raise LlmError("provider down")
        return ProviderResult(
            data={"score": 75, "arc": "climax", "justification": "ok"},
            provider=self.id,
            model="fake",
        )

    def generate_image(self, prompt, **kwargs):
        if self.fail:
            raise LlmError("no image")
        return [b"image"]


def test_router_falls_back_and_validates(monkeypatch) -> None:
    telemetry.reset()
    intelligence = Intelligence(AppSettings())
    providers = {
        "broken": _FakeProvider("broken", fail=True),
        "good": _FakeProvider("good"),
    }
    monkeypatch.setattr(intelligence, "_build_providers", lambda: providers)
    monkeypatch.setattr(intelligence, "_providers", providers, raising=False)
    intelligence.config.provider_order = ["broken", "good"]
    result = intelligence.complete_json(
        "curation.score",
        "prompt",
        "videoflow.short_score",
        validator=validate_score,
    )
    assert result.data["score"] == 75
    assert result.provider == "good"
    assert result.fallback == "provider_fallback"
    snapshot = telemetry.snapshot()
    assert snapshot["calls"] >= 1
    assert "curation.score" in snapshot["by_task"]


def test_router_reports_all_failures(monkeypatch) -> None:
    intelligence = Intelligence(AppSettings())
    providers = {"broken": _FakeProvider("broken", fail=True)}
    monkeypatch.setattr(intelligence, "_build_providers", lambda: providers)
    monkeypatch.setattr(intelligence, "_providers", providers, raising=False)
    intelligence.config.provider_order = ["broken"]
    with pytest.raises(IntelligenceError) as exc:
        intelligence.complete_json("curation.score", "prompt", "videoflow.short_score")
    assert "broken" in str(exc.value)


def test_llm_adapter_maps_schema_to_task(monkeypatch) -> None:
    intelligence = Intelligence(AppSettings())
    providers = {"good": _FakeProvider("good")}
    monkeypatch.setattr(intelligence, "_build_providers", lambda: providers)
    monkeypatch.setattr(intelligence, "_providers", providers, raising=False)
    intelligence.config.provider_order = ["good"]
    adapter = IntelligenceLlmAdapter(intelligence)
    data = adapter.complete_json("prompt", "videoflow.shorts")
    assert data["score"] == 75


def test_build_intelligence_has_a_status() -> None:
    intelligence = build_intelligence(AppSettings())
    assert isinstance(intelligence.status(), list)
