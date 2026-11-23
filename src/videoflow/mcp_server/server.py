"""VideoFlow MCP server with the production agent profile."""

from __future__ import annotations

import json
from typing import Any

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from videoflow.application.jobs import JobManager
from videoflow.mcp_server.agent_resources import register_agent_resources
from videoflow.mcp_server.context import ToolContext
from videoflow.mcp_server.core_tools import register_core_tools
from videoflow.mcp_server.guard import (
    error_envelope,
    mcp_tool_guard,
    suggest_parameters,
)
from videoflow.mcp_server.registry import (
    TOOL_DOCSTRINGS,
    TOOL_SPECS,
    profile_tool_names,
    validate_profile_registration,
    validate_tool_docstring,
)

SERVER_NAME = "VideoFlow"


class VideoFlowServer(MCPServer):
    """MCP server that rejects unknown tool keys before SDK validation."""

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Any = None,
    ) -> Any:
        tool = self._tool_manager.get_tool(name)
        if tool is not None and isinstance(arguments, dict):
            schema = tool.parameters or {}
            valid = set((schema.get("properties") or {}).keys())
            unknown = sorted(key for key in arguments if key not in valid)
            if unknown:
                first = unknown[0]
                exc = TypeError(
                    f"{name}() got an unexpected keyword argument '{first}'"
                )
                payload = error_envelope(exc, func=None)
                payload["message"] = (
                    "Unknown parameter(s): " + ", ".join(unknown)
                )
                payload["invalid_keys"] = unknown
                payload["did_you_mean"] = suggest_parameters(unknown, sorted(valid))
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=json.dumps(payload))
                    ],
                    structured_content=payload,
                    is_error=True,
                )
        return await super().call_tool(name, arguments, context)


def _annotations_for(name: str) -> ToolAnnotations:
    action = name.removeprefix("vf_").split("_")[0]
    destructive = ("delete", "remove", "cancel", "stop", "reset", "prune", "clear")
    read_only = {"vf_capabilities", "vf_catalog_search"}
    return ToolAnnotations(
        read_only_hint=name in read_only,
        destructive_hint=action in destructive,
        idempotent_hint=name in read_only or action in {"timeline", "artifact"},
        open_world_hint=action in {"ingest", "export", "exec"},
    )


def guard_tool(func: Any) -> Any:
    """Guarantee structured error payloads at the MCP boundary."""

    return mcp_tool_guard(func)


def build_server(
    jobs: JobManager | None = None,
    *,
    prompts: bool = True,
    profile: str = "core",
) -> MCPServer:
    """Build the agent-facing MCP server.

    ``profile`` selects the exact ``core`` (16) or ``full`` (21) surface. The
    internal ``all`` profile keeps every granular tool for the HTTP API and
    backward-compatible integrations. ``prompts=False`` skips the three
    ``videoflow_*`` prompts so channel instructions stay authoritative.
    """

    selected = set(profile_tool_names(profile))
    manager = jobs or JobManager()
    mcp = VideoFlowServer(SERVER_NAME)
    ctx = ToolContext(manager=manager)
    specs = {spec.name: spec for spec in TOOL_SPECS}
    registered: set[str] = set()

    def tool(func: Any) -> Any:
        spec = specs.get(func.__name__)
        if spec is None:
            raise RuntimeError(f"Missing TOOL_SPECS entry for {func.__name__}")
        if spec.name not in selected:
            return func
        doc = TOOL_DOCSTRINGS.get(spec.name)
        existing = str(func.__doc__ or "").strip()
        if doc:
            func.__doc__ = doc
        elif not all(
            marker in existing
            for marker in ("[DOES]", "[REQUIRES]", "[RETURNS]")
        ):
            func.__doc__ = (
                f"[DOES] {existing or spec.description}\n"
                "[REQUIRES] Tool-specific parameters.\n"
                "[RETURNS] Structured JSON result."
            )
        validate_tool_docstring(func)
        guarded = guard_tool(func)
        if not getattr(guarded, "__mcp_guarded__", False):
            raise RuntimeError(f"MCP tool {spec.name} is not guarded")
        registered.add(spec.name)
        return mcp.tool(
            name=spec.name,
            description=spec.description,
            annotations=_annotations_for(spec.name),
        )(guarded)

    register_core_tools(tool, ctx)
    validate_profile_registration(profile, registered)
    register_agent_resources(mcp, ctx, prompts=prompts)
    return mcp
