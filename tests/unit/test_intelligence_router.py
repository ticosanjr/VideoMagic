from __future__ import annotations

from types import SimpleNamespace

import pytest

from videoflow.application.intelligence import router
from videoflow.application.intelligence.models import (
    IntelligenceError,
    IntelligenceStatus,
    ProviderResult,
)
from videoflow.application.settings import AppSettings


def _result(data: dict | None = None) -> ProviderResult:
    return ProviderResult(
        data=data or {"ok": True},
        provider="p",
        model="m",
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=0.0,
        latency_ms=1,
    )


class Provider:
    kind = "fake"

    def __init__(self, ready=True, images=None, fail=False):
        self.ready = ready
        self.images = images or [b"image"]
        self.fail = fail

    def status(self):
        return IntelligenceStatus(
            provider="p", kind="fake", ready=self.ready, detail="ready"
        )

    def generate_image(self, prompt, **kwargs):
        if self.fail:
            raise RuntimeError("image failed")
        return self.images


def test_order_and_provider_lookup() -> None:
    intelligence = router.Intelligence(AppSettings())
    policy = SimpleNamespace(provider_order=["a", "b"])
    assert intelligence._order(policy, "") == ["a", "b"]
    assert intelligence._order(policy, "z") == ["z"]
    default = SimpleNamespace(provider_order=[])
    intelligence.config.provider_order = ["default"]
    assert intelligence._order(default, "") == ["default"]

    fake = Provider()
    intelligence._providers = {"named": fake, "kinded": fake}
    assert intelligence._provider("named") is fake
    assert intelligence._provider("fake") is fake
    assert intelligence._provider("missing") is None


def test_generate_image_returns_first_ready_provider(monkeypatch) -> None:
    intelligence = router.Intelligence(AppSettings())
    good = Provider(images=[b"one"])
    intelligence._providers = {"bad": Provider(ready=False), "good": good}
    intelligence.config.provider_order = ["bad", "good"]
    assert intelligence.generate_image("prompt") == [b"one"]


def test_generate_image_falls_back_and_reports_errors(monkeypatch) -> None:
    intelligence = router.Intelligence(AppSettings())
    intelligence._providers = {"bad": Provider(fail=True), "good": Provider(images=[b"ok"])}
    intelligence.config.provider_order = ["bad", "good"]
    assert intelligence.generate_image("prompt") == [b"ok"]

    intelligence._providers = {"bad": Provider(fail=True)}
    intelligence.config.provider_order = ["bad"]
    with pytest.raises(IntelligenceError, match="generate an image"):
        intelligence.generate_image("prompt")


def test_validated_handles_models_and_dicts() -> None:
    class Model:
        def model_dump(self, mode="json"):
            return {"value": 1}

    assert router._validated(lambda data: Model(), {}) == {"value": 1}
    assert router._validated(lambda data: {"value": 2}, {}) == {"value": 2}
    assert router._validated(lambda data: "bad", {"original": True}) == {
        "original": True
    }


def test_from_config_branches() -> None:
    intelligence = router.Intelligence(AppSettings())
    assert intelligence._from_config({"base_url": "", "model": ""}, "openai_compatible") is None
    compatible = intelligence._from_config(
        {
            "base_url": "http://127.0.0.1:1/v1",
            "model": "m",
            "id": "x",
            "api_key_env": "MISSING",
        },
        "openai_compatible",
    )
    assert compatible is not None
    assert compatible.id == "x"
    assert intelligence._from_config({}, "opencode_cli") is not None
    assert intelligence._from_config({}, "deepseek") is not None


def test_build_providers_from_environment(monkeypatch) -> None:
    intelligence = router.Intelligence(AppSettings())
    monkeypatch.setattr(router, "list_providers", lambda: [])
    monkeypatch.setenv("VIDEOWFLOW_OPENCODE_BIN", "/usr/bin/opencode")
    monkeypatch.setenv("VIDEOWFLOW_LLM_BASE_URL", "http://127.0.0.1:1/v1")
    monkeypatch.setenv("VIDEOWFLOW_LLM_MODEL", "model")
    providers = intelligence._build_providers()
    assert "opencode_cli" in providers
    assert "env_llm" in providers


def test_build_llm_adapter_only_when_available(monkeypatch) -> None:
    monkeypatch.setattr(
        router,
        "build_intelligence",
        lambda settings=None: SimpleNamespace(available=lambda: False),
    )
    assert router.build_llm_adapter() is None

    intelligence = SimpleNamespace(
        available=lambda: True,
        complete_json=lambda *args, **kwargs: _result(),
    )
    monkeypatch.setattr(router, "build_intelligence", lambda settings=None: intelligence)
    adapter = router.build_llm_adapter()
    assert adapter is not None
    assert adapter.complete_json("prompt", "videoflow.script") == {"ok": True}


def test_task_for_schema_maps_known_names() -> None:
    assert router._task_for_schema("videoflow.curation") == "curation.select"
    assert router._task_for_schema("videoflow.retakes") == "retakes.semantic"
    assert router._task_for_schema("videoflow.factcheck") == "factcheck.audit"
    assert router._task_for_schema("videoflow.other") == "generic"
