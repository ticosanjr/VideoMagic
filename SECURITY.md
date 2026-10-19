# Security policy

## Scope

VideoFlow is a local, single-user application. The supported security boundary is
one operating-system account and a loopback-only API. Exposing the port to a
network is outside the supported configuration.

## Reporting

Do not open a public issue with an exploit, a key, or private media. Contact the
repository owner privately. There is no dedicated security address yet; this is a
release blocker noted in `CHANGELOG.md`.

Include:

- affected version;
- a minimal reproduction with synthetic media;
- the impact;
- whether a secret or private file was exposed.

## Supported versions

Only the current minor release is supported while the project is pre-1.0.

## Known design constraints

- No authentication in v1. Loopback only.
- The path allowlist is the file-system boundary.
- LLM endpoints receive transcript text. A cloud provider is an explicit operator
  choice.
- A transcript can contain prompt-injection text. The product treats it as data
  and enforces deterministic retake rules, but a model can still be influenced.

## Hard rules for contributors

- No secret in state, presets, revisions, logs, errors, or tests.
- No path check based on string prefixes; use `resolve_allowed`.
- No world-writable media temp directory.
- No remote code or model download at test time.
- No disabling of the path jail for convenience.

See [docs/security.md](docs/security.md) for the full model.
