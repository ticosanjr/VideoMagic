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


def error(code: str, message: str) -> dict[str, object]:
    return {"ok": False, "code": code, "message": message}
