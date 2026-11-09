"""Shared delivery step helpers."""

from __future__ import annotations

from typing import Any

from videoflow.core.context import PipelineContext


def _result(context: PipelineContext) -> dict[str, Any]:
    return {"ok": True, "shorts": list(context.shorts), "artifacts": dict(context.artifacts)}
