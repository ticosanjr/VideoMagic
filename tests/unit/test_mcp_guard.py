from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel, ValidationError

from videoflow.domain.errors import VideoFlowError
from videoflow.mcp.guard import (
    error_envelope,
    mcp_tool_guard,
    normalize_execution,
)


def _tool(sentence_ids: list[int]) -> dict[str, object]:
    return {"ok": True, "sentence_ids": sentence_ids}


def test_guard_turns_validation_into_one_envelope() -> None:
    class Params(BaseModel):
        model_config = {"extra": "forbid"}

        sentence_ids: list[int]

    try:
        Params(sentence_id=[1])  # type: ignore[call-arg]
    except ValidationError as exc:
        payload = error_envelope(exc, func=_tool)
    assert payload["ok"] is False
    assert payload["error_code"] == "invalid_parameter"
    assert "sentence_id" in payload["invalid_keys"]
    assert payload["did_you_mean"] == ["sentence_ids"]
    assert payload["stderr_tail"] == ""


def test_guard_suggests_parameter_for_unexpected_keyword() -> None:
    wrapped = mcp_tool_guard(_tool)
    payload = wrapped(sentence_id=[1])
    assert payload["ok"] is False
    assert payload["invalid_keys"] == ["sentence_id"]
    assert payload["did_you_mean"] == ["sentence_ids"]
    assert "Error executing tool" not in str(payload)


def test_guard_preserves_videoflow_error_payload() -> None:
    class Failure(VideoFlowError):
        code = "gpu_worker_offline"

    @mcp_tool_guard
    def boom() -> dict[str, object]:
        raise Failure("worker is offline")

    payload = boom()
    assert payload["error_code"] == "gpu_worker_offline"
    assert payload["message"] == "worker is offline"
    assert payload["invalid_keys"] == []


def test_execution_is_never_empty() -> None:
    payload = normalize_execution({"ok": True, "execution": {}})
    assert payload["execution"]["execution_node"] == "local"
    assert payload["execution"]["degraded"] is False
    assert payload["execution"]["vram_peak_mb"] == 0


def test_execution_inside_job_is_filled() -> None:
    payload = normalize_execution({"ok": True, "job": {"id": "j1", "execution": {}}})
    assert payload["job"]["execution"]["device"] == "cpu"


def test_async_tool_is_guarded() -> None:
    @mcp_tool_guard
    async def async_tool() -> dict[str, object]:
        return {"ok": True, "execution": {}}

    payload = asyncio.run(async_tool())
    assert payload["execution"]["cache_hit"] is False


def test_guard_keeps_success_payload() -> None:
    wrapped = mcp_tool_guard(_tool)
    assert wrapped([1, 2]) == {"ok": True, "sentence_ids": [1, 2]}


@pytest.mark.parametrize("error", [RuntimeError("boom"), ValueError("bad")])
def test_unknown_errors_become_internal_error(error: Exception) -> None:
    def fail() -> None:
        raise error

    payload = mcp_tool_guard(fail)()
    assert payload["error_code"] == "internal_error"
    assert payload["message"] == str(error)
