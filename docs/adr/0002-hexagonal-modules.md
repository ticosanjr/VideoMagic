# ADR-0002 — Hexagonal boundaries and a fixed rack

Status: accepted. Date: 2026-10-19.

## Context

Three surfaces (UI, REST, MCP) share eight media modules. The brief describes a
rack, but leaves the execution graph and the boundary between routes and logic
open. If each surface implements its own orchestration, they will drift.

## Decision

- `domain/` is pure: time, state, planning, retake rules, timeline checks.
- Engine access is behind ports in `adapters/`.
- `application/` orchestrates; `api/` and `mcp_server/` are thin boundaries.
- The rack order is fixed: ingest, vad, transcribe, retakes, jl_cuts, zooms,
  shorts, export.
- A module declares `id`, `version`, `requires`, config, fingerprint, and execute.
- HTTP and MCP call the same service functions.

## Consequences

- The domain suite runs with no FFmpeg, model, or network.
- A new surface cannot invent edit logic without importing a service.
- The fixed order is less flexible than a free DAG. That is intentional: the
  product is a rack whose cache and UI depend on stable order.
- A module can be tested with a fake adapter.

## Alternatives rejected

- Fat route handlers: three copies of the retake guard.
- A free workflow DAG: more power than the product needs and much harder to
  explain in the UI.
- Putting MCP in the UI process only: agents need a local stdio path.
