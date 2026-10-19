# Contributing

## Before you start

Read [docs/prd.md](docs/prd.md), [docs/architecture.md](docs/architecture.md), and
the specification for the module you will touch. The ADRs explain why the
non-obvious rules exist.

Everything committed is English: code, comments, docstrings, logs, errors, UI
strings, commit messages, and documentation. Spoken media language is data, not
product language.

## Setup

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

UI:

```bash
cd ui
npm install
npm run check
npm run build
```

## Change shape

1. Open or reference an issue with the acceptance criterion.
2. Add a failing test. If the feature is specified but unbuilt, start with
   `xfail(strict=True)` and the AC id.
3. Implement the smallest slice.
4. Remove the marker in the same change.
5. Update the module spec, API doc, or manual that changed.
6. Add a `CHANGELOG.md` entry for user-visible changes.

## Rules

- Do not put business logic in `api/` or `mcp_server/`.
- Do not import FFmpeg, ONNX, HTTP, or MCP into `domain/`.
- Do not store a secret in state, a preset, a revision, or a log.
- Do not use float seconds for a cut, fade, offset, or export time.
- Do not add `mtime` to a cache hash.
- Do not guess an FCPXML attribute. Add the compatibility test.
- Do not edit a generated schema by hand. Run `scripts/export_schemas.py`.
- Do not commit media. Generate fixtures with FFmpeg.
- Do not leave an `xfail` that now passes; strict mode will fail the suite.

## Commits

`area: imperative summary`

Examples:

```
timebase: reject negative sample spans
mcp: register cancel_job
exporters: add xmeml straight-cut golden
docs: clarify Premiere dialect
```

One logical change per commit. Tests and docs travel with the code.

## Review checklist

- The contract test exists and is not xfail.
- Failure cases from the module spec are covered.
- Coverage has not dropped below the gate.
- `mypy` and ruff are clean.
- No secret, private path, or copyrighted media.
- The manual step, if any, is written down.
- The PRD and docs still describe the behavior.

## License

No license has been chosen. Do not add one without the owner's decision. Until
then, treat the repository as private.
