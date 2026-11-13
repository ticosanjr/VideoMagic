from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from videoflow.application.intelligence.providers.openai_compatible import (
    OpenAICompatibleProvider,
    _parse_json,
)
from videoflow.domain.errors import LlmError


def _provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        provider_id="test",
        base_url="http://127.0.0.1:1/v1",
        model="model",
        api_key="secret",
        retries=0,
    )


class Response:
    def __init__(self, status_code: int = 200, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


def test_status_and_parse_json() -> None:
    provider = _provider()
    assert provider.status().ready is True
    assert OpenAICompatibleProvider(base_url="", model="").status().ready is False
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        _parse_json("[1, 2]")


def test_complete_json_success_and_usage(monkeypatch) -> None:
    provider = _provider()
    monkeypatch.setattr(
        provider,
        "_post",
        lambda path, payload, timeout: Response(
            200,
            {
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        ),
    )
    result = provider.complete_json("hello", "schema")
    assert result.data == {"ok": True}
    assert result.prompt_tokens == 3
    assert result.completion_tokens == 2


def test_complete_json_retries_without_response_format(monkeypatch) -> None:
    provider = _provider()
    calls: list[dict] = []

    def post(path, payload, timeout):
        calls.append(payload)
        if "response_format" in payload:
            return Response(400, text="unsupported")
        return Response(200, {"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(provider, "_post", post)
    assert provider.complete_json("hello", "schema").data == {"ok": True}
    assert len(calls) == 2


def test_complete_json_error(monkeypatch) -> None:
    provider = _provider()
    monkeypatch.setattr(provider, "_post", lambda *args: Response(401, text="bad key"))
    with pytest.raises(LlmError, match="401"):
        provider.complete_json("hello", "schema")


def test_complete_json_with_images(tmp_path: Path, monkeypatch) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"png")
    provider = _provider()
    captured: dict = {}

    def post(path, payload, timeout):
        captured.update(payload)
        return Response(
            200,
            {"choices": [{"message": {"content": '{"issues": []}'}}]},
        )

    monkeypatch.setattr(provider, "_post", post)
    result = provider.complete_json_with_images("audit", [image], "schema")
    assert result.data == {"issues": []}
    content = captured["messages"][1]["content"]
    assert any(item["type"] == "image_url" for item in content)
    assert "data:image/png;base64," in content[1]["image_url"]["url"]

    with pytest.raises(LlmError):
        provider.complete_json_with_images("audit", [], "schema")


def test_generate_image_base64_and_url(tmp_path: Path, monkeypatch) -> None:
    provider = _provider()
    encoded = base64.b64encode(b"image").decode()
    responses = [
        Response(200, {"data": [{"b64_json": encoded}]}),
        Response(200, {"data": [{"url": "http://example.test/image.png"}]}),
    ]
    monkeypatch.setattr(provider, "_post", lambda *args: responses.pop(0))
    monkeypatch.setattr(
        "videoflow.application.intelligence.providers.openai_compatible.httpx.get",
        lambda *args, **kwargs: SimpleNamespace(status_code=200, content=b"downloaded"),
    )
    assert provider.generate_image("a") == [b"image"]
    assert provider.generate_image("a") == [b"downloaded"]


def test_generate_image_errors(monkeypatch) -> None:
    provider = _provider()
    monkeypatch.setattr(provider, "_post", lambda *args: Response(500, text="down"))
    with pytest.raises(LlmError):
        provider.generate_image("a")
    monkeypatch.setattr(provider, "_post", lambda *args: Response(200, {"data": []}))
    with pytest.raises(LlmError):
        provider.generate_image("a")


def test_post_raises_on_network_error(monkeypatch) -> None:
    provider = _provider()

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(
        "videoflow.application.intelligence.providers.openai_compatible.httpx.Client",
        lambda **kwargs: Client(),
    )
    with pytest.raises(LlmError, match="Cannot reach"):
        provider._post("/chat", {}, 1)
