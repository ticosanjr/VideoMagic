from __future__ import annotations

from videoflow.domain.errors import ExportError
from videoflow.mcp_server.server import guard_tool


def test_guard_tool_returns_typed_error_payload() -> None:
    def fail():
        raise ExportError("broken timeline")

    payload = guard_tool(fail)()
    assert payload["ok"] is False
    assert payload["error_code"] == "export_failed"
    assert payload["fix_hint"]


def test_guard_tool_returns_a_typed_error_payload() -> None:
    def fail():
        raise RuntimeError("unexpected")

    payload = guard_tool(fail)()
    assert payload["ok"] is False
    assert payload["error_code"] == "runtimeerror"
    assert payload["message"] == "unexpected"
    assert payload["last_frame"]


def test_guard_tool_preserves_successful_results() -> None:
    payload = guard_tool(lambda: {"ok": True})()
    assert payload["ok"] is True
    assert payload["_next_step"]
