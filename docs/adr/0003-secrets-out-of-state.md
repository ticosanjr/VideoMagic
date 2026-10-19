# ADR-0003 — Secrets never enter project state

Status: accepted. Date: 2026-10-19.

## Context

The brief lists `api_key` as a retake module parameter. Project state is written to
disk, copied for revisions, returned by an MCP resource, and attached to bug
reports. A key in that document would leak through every channel.

## Decision

- Config stores `secret_name`, not a value.
- The value is read from `VIDEOWFLOW_LLM_API_KEY` or `~/.videoflow/secrets.env`.
- The secrets file must be mode `0600`.
- Config models forbid unknown fields, so `api_key` is a validation error.
- Logs and MCP resources pass through `redact()`.
- A schema test asserts no public model exposes `api_key`.

## Consequences

- State and revisions are safe to share.
- A project is portable across machines without carrying credentials.
- The operator must provision the secret once per machine.
- A missing key fails the retake module with a typed error, not a fallback to an
  unauthenticated endpoint.
- Rotating a key does not invalidate cache, because the key is not part of module
  identity.

## Alternatives rejected

- Store the key encrypted in state: still shipped in revisions and MCP resources,
  and adds a key-management problem.
- `.env` in the project: too easy to commit, and the brief's own path rules would
  allow it to be served.
