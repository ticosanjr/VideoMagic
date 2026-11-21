"""VideoFlow MCP server with the production agent profile."""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from videoflow.application.jobs import JobManager
from videoflow.mcp.guard import mcp_tool_guard
from videoflow.mcp_server.agent_resources import register_agent_resources
from videoflow.mcp_server.context import ToolContext
from videoflow.mcp_server.core_tools import register_core_tools
from videoflow.mcp_server.registry import TOOL_SPECS

SERVER_NAME = "VideoFlow"


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
) -> MCPServer:
    """Build the agent-facing MCP server.

    ``prompts=False`` keeps the tools and resources but skips the three
    ``videoflow_*`` prompts so channel instructions stay authoritative.
    """

    manager = jobs or JobManager()
    mcp = MCPServer(SERVER_NAME)
    ctx = ToolContext(manager=manager)
    specs = {spec.name: spec for spec in TOOL_SPECS}

    def tool(func: Any) -> Any:
        spec = specs.get(func.__name__)
        if spec is None:
            raise RuntimeError(f"Missing TOOL_SPECS entry for {func.__name__}")
        return mcp.tool(
            name=spec.name,
            description=spec.description,
            annotations=_annotations_for(spec.name),
        )(guard_tool(func))

    register_core_tools(tool, ctx)
    register_agent_resources(mcp, ctx, prompts=prompts)
    return mcp
