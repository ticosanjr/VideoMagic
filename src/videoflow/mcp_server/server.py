"""MCP server. Tools operate on loaded media, pending config, and real job state."""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from videoflow.application.jobs import JobManager
from videoflow.engine.batch import BatchManager
from videoflow.mcp_server.context import ToolContext
from videoflow.mcp_server.prompts_resources import register_prompts_resources
from videoflow.mcp_server.registry import TOOL_SPECS
from videoflow.mcp_server.tools_config import register_config_tools
from videoflow.mcp_server.tools_jobs import register_job_tools
from videoflow.mcp_server.tools_media import register_media_tools
from videoflow.mcp_server.tools_shorts import register_short_tools
from videoflow.mcp_server.tools_timeline import register_timeline_tools

SERVER_NAME = "VideoFlow"


def _annotations_for(name: str) -> ToolAnnotations:
    """Return the behavior hints for one public tool name."""

    action = name.removeprefix("videoflow_").split("_")[0]
    destructive = ("delete", "remove", "cancel", "stop", "reset", "prune", "clear")
    read_only = ("list", "get", "validate", "metrics", "cost", "capabilities", "doctor")
    return ToolAnnotations(
        read_only_hint=action in read_only,
        destructive_hint=action in destructive,
        idempotent_hint=action in read_only or action in {"save", "set", "pause", "unpause"},
        open_world_hint=action in {"import", "upload", "transcribe", "generate", "analyze"},
    )


def build_server(
    jobs: JobManager | None = None,
    batches: BatchManager | None = None,
) -> MCPServer:
    """Build the MCP server and register every tool, prompt, and resource."""
    manager = jobs or JobManager()
    batch_manager = batches or BatchManager(manager)
    mcp = MCPServer(SERVER_NAME)
    ctx = ToolContext(manager=manager, batch_manager=batch_manager)
    specs = {spec.name: spec for spec in TOOL_SPECS}

    def tool(func: Any) -> Any:
        spec = specs.get(func.__name__)
        if spec is None:
            raise RuntimeError(f"Missing TOOL_SPECS entry for {func.__name__}")
        return mcp.tool(
            name=spec.name,
            description=spec.description,
            annotations=_annotations_for(spec.name),
        )(func)

    register_config_tools(tool, ctx)
    register_media_tools(tool, ctx)
    register_short_tools(tool, ctx)
    register_job_tools(tool, ctx)
    register_timeline_tools(tool, ctx)
    register_prompts_resources(mcp, ctx)

    mcp.videoflow_last = ctx.last  # type: ignore[attr-defined]
    return mcp
