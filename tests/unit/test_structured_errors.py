from __future__ import annotations

from videoflow.domain.errors import ExportError, IngestError
from videoflow.mcp_server.context import error


def test_mcp_error_payload_has_required_fields() -> None:
    payload = error(
        "export_failed",
        "render failed",
        failed_command="ffmpeg -i x",
        stderr_tail="bad frame",
        fix_hint="check the source",
    )
    assert payload["ok"] is False
    assert payload["error_code"] == "export_failed"
    assert payload["failed_command"] == "ffmpeg -i x"
    assert payload["stderr_tail"] == "bad frame"
    assert payload["fix_hint"] == "check the source"


def test_typed_errors_expose_command_and_stderr() -> None:
    error = IngestError(
        "ffmpeg failed",
        command="ffmpeg -i x",
        stderr="decoder error",
        returncode=1,
    )
    payload = error.to_dict()
    assert payload["error_code"] == "ingest_failed"
    assert payload["failed_command"] == "ffmpeg -i x"
    assert "decoder error" in str(payload["stderr_tail"])
    assert payload["fix_hint"]

    exported = ExportError("timeline broken").to_dict()
    assert exported["error_code"] == "export_failed"
    assert "failed_command" in exported
    assert "fix_hint" in exported
