# ADR-0009 — Local single-user runtime

Status: accepted. Date: 2026-10-19.

## Context

The brief describes a local tool: a path on disk, a local UI, and local agents.
It does not define authentication, tenancy, or a queue. The file-based project
layout already implies one operator.

## Decision

- Bind to `127.0.0.1`. No login in v1.
- One process, one project lock, one active job per project.
- The path allowlist is the security boundary.
- Jobs are in-process; long native work runs in subprocesses.
- No database, broker, or container is required.

## Consequences

- Simple install and debugging.
- The API must not be exposed to a network.
- A shared server would need authentication, per-user roots, and a real queue.
  Those are a new product decision, not a configuration flag.
- The UI origin allowlist is explicit, not `*`.

## Alternatives rejected

- Token auth in v1: adds friction without a remote threat model.
- Multi-user now: large scope, no stated requirement.
- Celery/Redis: operational weight with no benefit for one editor.
