"""Crash reports and token accounting."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from videoflow.adapters.llm import OpenAICompatibleLlm
from videoflow.application import cost
from videoflow.application.crash import write_crash_report


def test_crash_report_contains_no_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        target = write_crash_report(exc, where="test")

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["type"] == "RuntimeError"
    assert payload["message"] == "boom"
    assert "Traceback" in payload["traceback"]
    assert "videowflow" not in json.dumps(payload).lower()
    assert "home" not in payload


def test_llm_usage_is_accumulated(monkeypatch: pytest.MonkeyPatch) -> None:
    cost.reset()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            },
        )

    client = OpenAICompatibleLlm(
        base_url="http://test.invalid/v1",
        model="model-a",
        transport=httpx.MockTransport(handler),
    )

    assert client.complete_json("hi", "test") == {"ok": True}
    usage = cost.snapshot()

    assert usage["calls"] == 1
    assert usage["prompt_tokens"] == 12
    assert usage["completion_tokens"] == 4
    assert usage["by_model"]["model-a"]["calls"] == 1


def test_unhandled_http_error_writes_a_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from fastapi.testclient import TestClient

    from videoflow.api.app import create_app

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    app = create_app()

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "internal_error"
    assert Path(body["details"]["report"]).is_file()
