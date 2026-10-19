# ADR-0005 — stdio primary, Streamable HTTP mounted

Status: accepted. Date: 2026-10-19.

## Context

The brief requires stdio and SSE. The MCP ecosystem has moved to Streamable HTTP;
SSE is the superseded transport. Local agents (OpenCode, Cursor, Claude Desktop)
still prefer stdio. The API is already a FastAPI process.

## Decision

- Use the official Python SDK v2 (`MCPServer`).
- Primary: stdio via `videoflow-mcp`.
- Secondary: Streamable HTTP at `/mcp`, mounted in the FastAPI app.
- Enable SSE only through the SDK's legacy path if a host requires it.
- Mounting requires the host lifespan to run `mcp.session_manager`.
- Tools return structured data; protocol errors are reserved for transport faults.

## Consequences

- One process can serve the UI and HTTP agents.
- The stdio command does not need the HTTP server.
- The mount path is `/mcp`; mounting at `/` would shadow every route, so health
  and future API routes are registered first.
- The combined app is tested, not assumed. The scaffold verifies `/health` and
  tool listing.

## Alternatives rejected

- SSE only: deprecated and worse for reconnects.
- stdio only: browser clients cannot use it.
- A separate HTTP process: two lifecycles and two job stores.
