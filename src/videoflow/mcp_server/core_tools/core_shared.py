"""Helpers shared by the core MCP tool modules."""

from __future__ import annotations

import contextlib
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from videoflow.application.projects import get_project
from videoflow.domain.errors import VideoFlowError
from videoflow.mcp_server.agent_helpers import _job_payload
from videoflow.mcp_server.agent_tools import register_agent_tools
from videoflow.mcp_server.context import error
from videoflow.steps.registry import iter_steps


def _capture_legacy(register: Any, ctx: Any) -> dict[str, Any]:
    tools: dict[str, Any] = {}

    def capture(func: Any) -> Any:
        tools[func.__name__] = func
        return func

    register_agent_tools(capture, ctx)
    return tools


@lru_cache(maxsize=1)
def _step_catalog() -> tuple[dict[str, Any], ...]:
    """Build the static step catalog once per process."""

    return tuple(
        {
            "type": step.type,
            "title": step.title,
            "description": step.description,
            "status": step.status,
            "requires": list(step.requires),
            "produces": list(step.produces),
            "schema_resource": f"vf://docs/steps/{step.type}",
        }
        for step in iter_steps()
    )


def _is_step(step_type: str) -> bool:
    from videoflow.steps.registry import get_step

    try:
        get_step(step_type)
        return True
    except VideoFlowError:
        return False


def _wait(manager: Any, project_id: str, job_id: str, timeout: float) -> dict[str, Any]:
    record = get_project(project_id)
    job = manager.get(job_id)
    if getattr(job, "project_id", "") not in {"", record.project_id}:
        return error("job_mismatch", "Job does not belong to this project")
    deadline = time.monotonic() + max(1.0, min(3600.0, timeout))
    terminal = {"succeeded", "failed", "cancelled", "answered", "needs_review"}
    while job.status not in terminal:
        if time.monotonic() >= deadline:
            return {"ok": False, "code": "timeout", "job": _job_payload(job)}
        heartbeat = getattr(manager, "heartbeat", None)
        if callable(heartbeat):
            with contextlib.suppress(Exception):
                heartbeat(job_id)
        time.sleep(0.5)
        job = manager.get(job_id)
    return {"ok": job.status == "succeeded", "job": _job_payload(job)}


def _fps_int(value: int | str | None) -> int | None:
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
        return number if number > 0 else None
    return None


def _short_clip_for_video(output: Path, video: Path) -> dict[str, Any] | None:
    """Find the Short manifest entry that owns ``video``."""

    import json

    target = Path(video).expanduser().resolve()
    for relative in (
        "shorts/batch/shorts_batch.json",
        "shorts/shorts_batch.json",
        "shorts.json",
    ):
        path = Path(output) / relative
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        clips = payload.get("clips") if isinstance(payload, dict) else None
        if not isinstance(clips, list):
            continue
        for clip in clips:
            if not isinstance(clip, dict) or not clip.get("path"):
                continue
            with contextlib.suppress(OSError):
                if Path(str(clip["path"])).expanduser().resolve() == target:
                    return clip
    return None
