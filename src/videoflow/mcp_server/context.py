"""Shared state for MCP tool registration."""

from __future__ import annotations

from dataclasses import dataclass

from videoflow.application.jobs import JobManager
from videoflow.engine.batch import BatchManager


@dataclass(slots=True)
class ToolContext:
    """Application services shared by every agent-facing tool."""

    manager: JobManager
    batch_manager: BatchManager


def error(
    code: str,
    message: str,
    *,
    failed_command: str = "",
    stderr_tail: str = "",
    fix_hint: str = "",
    **details: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "ok": False,
        "code": code,
        "error_code": code,
        "message": message,
        "failed_command": failed_command,
        "stderr_tail": stderr_tail[-4000:],
        "fix_hint": fix_hint,
    }
    if details:
        payload["details"] = details
    return payload
