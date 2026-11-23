import pytest

from videoflow.application import capabilities as capability_module
from videoflow.application.capabilities import (
    capability_manifest,
    clear_capability_cache,
    ensure_external_allowed,
    external_services_allowed,
)
from videoflow.domain.errors import CapabilityUnavailableError


def test_external_policy_allows_local_and_requires_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOWFLOW_ALLOW_EXTERNAL", raising=False)
    assert external_services_allowed(True) is True
    assert external_services_allowed(False) is False
    ensure_external_allowed(
        "http://localhost:11434/v1",
        capability="external_llm",
        allow_external_services=False,
    )
    with pytest.raises(CapabilityUnavailableError):
        ensure_external_allowed(
            "https://api.example.com/v1",
            capability="external_llm",
            allow_external_services=False,
        )
    with pytest.raises(CapabilityUnavailableError, match="not in allowed_external_hosts"):
        ensure_external_allowed(
            "https://api.example.com/v1",
            capability="external_llm",
            allow_external_services=True,
            allowed_hosts=["other.example.com"],
        )
    ensure_external_allowed(
        "https://api.example.com/v1",
        capability="external_llm",
        allow_external_services=True,
        allowed_hosts=["api.example.com"],
    )


def test_global_kill_switch_wins_even_for_external_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOW_EXTERNAL", "0")
    assert external_services_allowed(True) is False
    with pytest.raises(CapabilityUnavailableError):
        ensure_external_allowed(
            "https://api.example.com/v1",
            capability="external_llm",
            allow_external_services=True,
        )
    ensure_external_allowed(
        "http://127.0.0.1:8000/v1",
        capability="external_llm",
        allow_external_services=True,
    )


def test_manifest_marks_external_providers_blocked_by_default() -> None:
    entries = {entry["id"]: entry for entry in capability_manifest()}
    assert entries["shorts_aspects"]["status"] == "available"
    assert entries["shorts_timeframe"]["status"] == "available"
    assert entries["external_llm"]["status"] == "blocked"
    assert "External services are disabled" in str(entries["external_llm"]["reason"])
    assert entries["shorts_editor"]["status"] == "available"
    assert entries["prompt_to_clip"]["status"] == "available"
    assert entries["reprompt"]["status"] == "available"
    assert entries["auto_hook"]["status"] == "available"
    assert entries["virality_score"]["status"] == "partial"


def test_manifest_is_cached_briefly_and_returns_copies(monkeypatch) -> None:
    calls: list[int] = []

    def compute_entry() -> dict[str, object]:
        calls.append(1)
        return {"id": "compute_router", "status": "available"}

    monkeypatch.setattr(capability_module, "_compute_entry", compute_entry)
    clear_capability_cache()
    first = capability_manifest()
    first[0]["id"] = "mutated"
    second = capability_manifest()
    assert len(calls) == 1
    assert second[0]["id"] != "mutated"

    clear_capability_cache()
    capability_manifest()
    assert len(calls) == 2
    clear_capability_cache()


def test_manifest_mcp_names_are_exposed_by_the_full_profile() -> None:
    from videoflow.mcp_server.registry import profile_tool_names

    names = set(profile_tool_names("full")) | {"", "not exposed"}
    clear_capability_cache()
    for entry in capability_manifest():
        assert entry["mcp"] in names, entry["id"]
