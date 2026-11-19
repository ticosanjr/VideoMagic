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


def test_guard_tool_returns_internal_error_payload() -> None:
    def fail():
        raise RuntimeError("unexpected")

    payload = guard_tool(fail)()
    assert payload["ok"] is False
    assert payload["error_code"] == "internal_error"
    assert payload["message"] == "unexpected"


def test_guard_tool_preserves_successful_results() -> None:
    assert guard_tool(lambda: {"ok": True})() == {"ok": True}
