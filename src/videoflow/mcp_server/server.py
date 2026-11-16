"""VideoFlow MCP server with the production agent profile."""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from videoflow.application.jobs import JobManager
from videoflow.engine.batch import BatchManager
from videoflow.mcp_server.agent_resources import register_agent_resources
from videoflow.mcp_server.agent_tools import register_agent_tools
from videoflow.mcp_server.context import ToolContext
from videoflow.mcp_server.registry import TOOL_SPECS

SERVER_NAME = "VideoFlow"


def _annotations_for(name: str) -> ToolAnnotations:
    action = name.removeprefix("vf_").split("_")[0]
    destructive = ("delete", "remove", "cancel", "stop", "reset", "prune", "clear")
    read_only = ("project", "capabilities", "list", "get", "validate", "wait")
    return ToolAnnotations(
        read_only_hint=action in read_only,
        destructive_hint=action in destructive,
        idempotent_hint=action in read_only or action in {"edit", "sync"},
        open_world_hint=action in {"ingest", "render", "nle"},
    )


def build_server(
    jobs: JobManager | None = None,
    batches: BatchManager | None = None,
) -> MCPServer:
    """Build the agent-facing MCP server."""

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
            structured_output=(
                False if spec.name in {"vf_get_artifact", "vf_get_qa_artifacts"} else None
            ),
        )(func)

    register_agent_tools(tool, ctx)
    register_agent_resources(mcp, ctx)
    return mcp
