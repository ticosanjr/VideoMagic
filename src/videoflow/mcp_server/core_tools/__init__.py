"""Consolidated core MCP surface for VideoFlow."""

from __future__ import annotations

from typing import Any

from videoflow.mcp_server.format_tools import register_format_tools
from videoflow.mcp_server.scene_tools import register_scene_tools

from . import (
    core_audio_vision,
    core_export,
    core_fx,
    core_insights,
    core_jobs,
    core_media,
    core_overlays,
    core_projects,
    core_qa,
    core_styles,
    core_timeline,
)
from .core_shared import _capture_legacy, _wait
from .official import register_official_tools

_MODULES = (
    core_styles,
    core_overlays,
    core_fx,
    core_media,
    core_audio_vision,
    core_qa,
    core_insights,
    core_projects,
    core_jobs,
    core_timeline,
    core_export,
)


def register_core_tools(register: Any, ctx: Any) -> None:
    legacy = _capture_legacy(register, ctx)
    tools: dict[str, Any] = {}

    def capture(func: Any) -> Any:
        tools[func.__name__] = func
        return register(func)

    for module in _MODULES:
        module.register(capture, ctx, legacy)
    register_scene_tools(capture, ctx, wait_fn=_wait)
    register_format_tools(capture)
    register_official_tools(capture, tools)


__all__ = ["register_core_tools"]
