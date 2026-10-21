import pytest

from videoflow.application.capabilities import (
    capability_manifest,
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
    assert entries["shorts_editor"]["status"] == "planned"
