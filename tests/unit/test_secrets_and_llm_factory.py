"""Secret backends and LLM client construction."""

from __future__ import annotations

import json
import stat

import pytest

from videoflow.adapters.llm import FallbackLlm
from videoflow.application import llm_factory, secrets
from videoflow.application.circuit import CircuitBreakerLlm
from videoflow.domain.errors import CapabilityUnavailableError


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.fail = False

    def get_password(self, service: str, name: str) -> str | None:
        if self.fail:
            raise RuntimeError("keyring unavailable")
        return self.values.get((service, name))

    def set_password(self, service: str, name: str, value: str) -> None:
        if self.fail:
            raise RuntimeError("keyring unavailable")
        self.values[(service, name)] = value

    def delete_password(self, service: str, name: str) -> None:
        if self.fail:
            raise RuntimeError("keyring unavailable")
        self.values.pop((service, name), None)

    def get_keyring(self) -> object:
        return SimpleBackend()


class SimpleBackend:
    pass


def test_environment_wins_over_every_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keyring = FakeKeyring()
    keyring.values[(secrets.SERVICE, "TOKEN")] = "from-keyring"
    monkeypatch.setattr(secrets, "_keyring", lambda: keyring)
    monkeypatch.setenv("TOKEN", "from-env")

    assert secrets.get_secret("TOKEN") == "from-env"


def test_keyring_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    keyring = FakeKeyring()
    monkeypatch.setattr(secrets, "_keyring", lambda: keyring)

    secrets.set_secret("TOKEN", "value")

    assert keyring.values[(secrets.SERVICE, "TOKEN")] == "value"
    assert secrets.get_secret("TOKEN") == "value"
    assert secrets.secret_present("TOKEN") is True
    assert not secrets._fallback_path().exists()

    secrets.delete_secret("TOKEN")

    assert secrets.get_secret("TOKEN") == ""


def test_keyring_errors_fall_back_to_a_0600_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keyring = FakeKeyring()
    keyring.fail = True
    monkeypatch.setattr(secrets, "_keyring", lambda: keyring)

    secrets.set_secret("TOKEN", "value")

    path = secrets._fallback_path()
    assert json.loads(path.read_text(encoding="utf-8")) == {"TOKEN": "value"}
    assert stat.S_IMODE(path.stat().st_mode) == stat.S_IRUSR | stat.S_IWUSR
    assert secrets.get_secret("TOKEN") == "value"

    secrets.delete_secret("TOKEN")
    assert secrets.get_secret("TOKEN") == ""


def test_empty_names_and_corrupt_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(secrets, "_keyring", lambda: None)
    assert secrets.get_secret("") == ""
    with pytest.raises(ValueError, match="name is empty"):
        secrets.set_secret("", "value")

    path = secrets._fallback_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json", encoding="utf-8")
    assert secrets.get_secret("TOKEN") == ""


def test_secret_backend_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(secrets, "_keyring", lambda: None)
    assert secrets.secret_backend() == "file:0600"

    monkeypatch.setattr(secrets, "_keyring", lambda: FakeKeyring())
    assert secrets.secret_backend() == "keyring:SimpleBackend"


def test_llm_factory_prefers_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("VIDEOWFLOW_LLM_MODEL", "env-model")
    monkeypatch.setattr(llm_factory, "resolve_chain", lambda _capability: [])
    monkeypatch.setattr(llm_factory, "get_secret", lambda _name: "")

    client = llm_factory.build_llm()

    assert isinstance(client, CircuitBreakerLlm)


def test_llm_factory_uses_provider_chain_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VIDEOWFLOW_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("VIDEOWFLOW_LLM_MODEL", raising=False)
    monkeypatch.setattr(
        llm_factory,
        "resolve_chain",
        lambda _capability: [
            {"base_url": "http://a/v1", "model": "a"},
            {"base_url": "http://b/v1", "model": "b"},
            {"base_url": "http://c/v1", "model": ""},
        ],
    )
    monkeypatch.setattr(llm_factory, "get_secret", lambda name: f"key-{name}")

    client = llm_factory.build_llm()

    assert isinstance(client, FallbackLlm)


def test_llm_factory_requires_a_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIDEOWFLOW_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("VIDEOWFLOW_LLM_MODEL", raising=False)
    monkeypatch.setattr(llm_factory, "resolve_chain", lambda _capability: [])

    with pytest.raises(CapabilityUnavailableError):
        llm_factory.build_llm()


def test_settings_are_loaded_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("VIDEOWFLOW_LLM_MODEL", "env-model")
    calls: list[str] = []

    class Settings:
        class llm:
            timeout_seconds = 12
            temperature = 0.2
            max_tokens = 100
            retries = 1

    monkeypatch.setattr(llm_factory, "resolve_chain", lambda _capability: [])
    monkeypatch.setattr(llm_factory, "load_settings", lambda: calls.append("load") or Settings)

    llm_factory.build_llm()

    assert calls == ["load"]
