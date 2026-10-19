import json

import httpx
import pytest

from videoflow.adapters.llm import OpenAICompatibleLlm
from videoflow.domain.errors import LlmError


def test_successful_json_call_sends_auth_and_temperature() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"discard_sentence_ids": [1], "reasoning": "x"}'}}
                ]
            },
        )

    client = OpenAICompatibleLlm(
        base_url="http://llm.local/v1",
        model="qwen",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )
    result = client.complete_json("prompt", "retakes")
    assert result["discard_sentence_ids"] == [1]
    assert seen["auth"] == "Bearer secret"
    assert seen["body"]["temperature"] == 0
    assert seen["body"]["response_format"] == {"type": "json_object"}


def test_retry_without_response_format_on_400() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        body = json.loads(request.content)
        if "response_format" in body:
            return httpx.Response(400, json={"error": "unsupported"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"discard_sentence_ids": [], "reasoning": "ok"}'}}
                ]
            },
        )

    client = OpenAICompatibleLlm(
        base_url="http://llm.local/v1", model="qwen", transport=httpx.MockTransport(handler)
    )
    assert client.complete_json("prompt", "retakes")["reasoning"] == "ok"
    assert calls["count"] == 2


def test_code_fences_are_stripped() -> None:
    fenced = '```json\n{"discard_sentence_ids": [], "reasoning": "ok"}\n```'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": fenced}}]},
        )

    client = OpenAICompatibleLlm(
        base_url="http://llm.local/v1", model="qwen", transport=httpx.MockTransport(handler)
    )
    assert client.complete_json("prompt", "retakes")["reasoning"] == "ok"


def test_http_error_does_not_echo_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = OpenAICompatibleLlm(
        base_url="http://llm.local/v1",
        model="qwen",
        api_key="super-secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LlmError) as caught:
        client.complete_json("prompt", "retakes")
    assert "super-secret" not in str(caught.value)


def test_unusable_json_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "no json"}}]})

    client = OpenAICompatibleLlm(
        base_url="http://llm.local/v1", model="qwen", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(LlmError):
        client.complete_json("prompt", "retakes")
