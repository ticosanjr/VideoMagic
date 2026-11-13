from __future__ import annotations

import httpx
import pytest

from videoflow.application.intelligence.providers.opencode_v2 import (
    OpenCodeV2Provider,
    _parse_json,
)
from videoflow.domain.errors import LlmError


def _select(model="", types="chat"):
    return {"id": "m", "providerID": "p"}


class Response:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


def _provider() -> OpenCodeV2Provider:
    return OpenCodeV2Provider(base_url="http://127.0.0.1:1", model="model", retries=0)


def test_status_paths(monkeypatch) -> None:
    assert OpenCodeV2Provider(base_url="").status().ready is False
    provider = _provider()
    monkeypatch.setattr(provider, "_request", lambda *args, **kwargs: Response(200))
    assert provider.status().ready is True
    monkeypatch.setattr(provider, "_request", lambda *args, **kwargs: Response(500))
    assert provider.status().ready is False
    monkeypatch.setattr(
        provider,
        "_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(LlmError("down")),
    )
    assert "down" in (provider.status().detail or "")


def test_complete_json_success_and_errors(monkeypatch) -> None:
    provider = _provider()
    monkeypatch.setattr(provider, "_select_model", _select)
    monkeypatch.setattr(
        provider,
        "_request",
        lambda *args, **kwargs: Response(
            200, {"data": {"text": '{"ok": true}'}}
        ),
    )
    result = provider.complete_json("prompt", "schema")
    assert result.data == {"ok": True}
    assert result.model == "p/m"

    monkeypatch.setattr(provider, "_request", lambda *args, **kwargs: Response(401, text="bad"))
    with pytest.raises(LlmError, match="401"):
        provider.complete_json("prompt", "schema")
    monkeypatch.setattr(
        provider, "_request", lambda *args, **kwargs: Response(200, {"data": {}})
    )
    with pytest.raises(LlmError, match="unusable"):
        provider.complete_json("prompt", "schema")


def test_generate_image_paths(monkeypatch) -> None:
    provider = _provider()
    monkeypatch.setattr(provider, "_select_model", _select)
    encoded = "aW1hZ2U="
    monkeypatch.setattr(
        provider,
        "_request",
        lambda *args, **kwargs: Response(
            200, {"data": {"images": [{"data": encoded}]}}
        ),
    )
    assert provider.generate_image("prompt") == [b"image"]

    monkeypatch.setattr(
        provider, "_request", lambda *args, **kwargs: Response(500, text="bad")
    )
    with pytest.raises(LlmError):
        provider.generate_image("prompt")
    monkeypatch.setattr(
        provider,
        "_request",
        lambda *args, **kwargs: Response(200, {"data": {"images": []}}),
    )
    with pytest.raises(LlmError):
        provider.generate_image("prompt")


def test_select_model_and_list_models(monkeypatch) -> None:
    provider = _provider()
    provider._models["chat"] = [{"id": "a", "providerID": "p", "enabled": True}]
    assert provider._select_model("a")["id"] == "a"
    assert provider._select_model("p/a")["id"] == "a"
    provider._models["chat"] = [{"id": "a", "providerID": "p", "enabled": False}]
    with pytest.raises(LlmError):
        provider._select_model("a")

    monkeypatch.setattr(
        provider,
        "_request",
        lambda *args, **kwargs: Response(
            200, {"data": [{"id": "a", "providerID": "p", "enabled": True}]}
        ),
    )
    assert provider.list_models()[0]["id"] == "a"
    provider._models.clear()
    monkeypatch.setattr(provider, "_request", lambda *args, **kwargs: Response(500))
    with pytest.raises(LlmError):
        provider.list_models()


def test_request_retries_and_errors(monkeypatch) -> None:
    provider = OpenCodeV2Provider(base_url="http://127.0.0.1:1", retries=1)
    calls = {"n": 0}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ConnectError("down")
            return Response(200)

    monkeypatch.setattr(
        "videoflow.application.intelligence.providers.opencode_v2.httpx.Client",
        lambda **kwargs: Client(),
    )
    assert provider._request("GET", "/api/info", timeout=1).status_code == 200
    assert calls["n"] == 2

    provider = OpenCodeV2Provider(base_url="http://127.0.0.1:1", retries=0)

    class Down:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, *args, **kwargs):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(
        "videoflow.application.intelligence.providers.opencode_v2.httpx.Client",
        lambda **kwargs: Down(),
    )
    with pytest.raises(LlmError, match="Cannot reach"):
        provider._request("GET", "/api/info", timeout=1)


def test_parse_json_and_headers(monkeypatch) -> None:
    assert _parse_json("```json\n{\"a\": 1}\n```") == {"a": 1}
    with pytest.raises(ValueError):
        _parse_json("[]")
    provider = OpenCodeV2Provider(base_url="http://x", token="secret")
    monkeypatch.setattr(
        provider,
        "_request",
        lambda *args, **kwargs: Response(200),
    )
    assert provider.status().ready is True
