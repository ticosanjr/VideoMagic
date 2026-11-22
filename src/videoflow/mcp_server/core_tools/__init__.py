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
    for module in _MODULES:
        module.register(register, ctx, legacy)
    register_scene_tools(register, ctx, wait_fn=_wait)
    register_format_tools(register)


__all__ = ["register_core_tools"]
