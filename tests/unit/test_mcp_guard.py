from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel, ValidationError

from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.guard import (
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
    assert payload["error_code"] == "invalid_params"
    assert "sentence_id" in payload["invalid_keys"]
    assert payload["did_you_mean"] == {"sentence_id": "sentence_ids"}
    assert payload["stderr_tail"] == ""


def test_guard_suggests_parameter_for_unexpected_keyword() -> None:
    wrapped = mcp_tool_guard(_tool)
    payload = wrapped(sentence_id=[1])
    assert payload["ok"] is False
    assert payload["invalid_keys"] == ["sentence_id"]
    assert payload["did_you_mean"] == {"sentence_id": "sentence_ids"}
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
    payload = wrapped([1, 2])
    assert payload["ok"] is True
    assert payload["sentence_ids"] == [1, 2]
    assert payload["_next_step"]


@pytest.mark.parametrize("error", [RuntimeError("boom"), ValueError("bad")])
def test_unknown_errors_become_internal_error(error: Exception) -> None:
    def fail() -> None:
        raise error

    payload = mcp_tool_guard(fail)()
    assert payload["error_code"] == "internal_error"
    assert payload["message"] == str(error)


def test_unknown_key_returns_the_documented_envelope() -> None:
    def vf_layout(margin_y: int = 32, project_id: str = "") -> dict[str, object]:
        return {"ok": True}

    payload = mcp_tool_guard(vf_layout)(project_id="p", margin_top=10)
    assert payload == {
        "ok": False,
        "error_code": "invalid_params",
        "code": "invalid_params",
        "message": payload["message"],
        "invalid_keys": ["margin_top"],
        "did_you_mean": {"margin_top": "margin_y"},
        "failed_command": "",
        "stderr_tail": "",
        "fix_hint": "Use the exact parameter names from the tool schema.",
    }


def test_success_payloads_get_the_next_step_and_compact_lists() -> None:
    @mcp_tool_guard
    def vf_jobs(action: str = "list") -> dict[str, object]:
        return {"ok": True, "jobs": list(range(35))}

    payload = vf_jobs()
    assert payload["_next_step"]
    assert len(payload["jobs"]) == 30
    assert payload["truncated"] is True
    assert payload["truncated_fields"] == {"jobs": 35}
    assert payload["total_count"] == 35
    assert payload["next_offset"] == 30


def test_tool_specific_next_step_wins() -> None:
    @mcp_tool_guard
    def vf_curation(action: str = "read") -> dict[str, object]:
        return {"ok": True, "status": "waiting_human", "_next_step": "custom"}

    assert vf_curation()["_next_step"] == "custom"


def test_error_payloads_do_not_get_a_next_step() -> None:
    @mcp_tool_guard
    def vf_jobs(action: str = "get") -> dict[str, object]:
        return {"ok": False, "code": "job_not_found"}

    assert "_next_step" not in vf_jobs()
