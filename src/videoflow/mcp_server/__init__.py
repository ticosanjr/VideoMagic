"""MCP boundary. Tools call application services; they do not edit timelines themselves."""

from videoflow.mcp_server.server import build_server

__all__ = ["build_server"]
