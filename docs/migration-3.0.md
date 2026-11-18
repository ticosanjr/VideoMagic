# Migration to 3.0.0

VideoFlow 3.0.0 keeps recipes in the UI, CLI, and REST API while removing them
from MCP. Projects and styles remain compatible.

## Styles

- `schema_version` 1 is still readable.
- New files are written as `schema_version: 2`.
- New optional fields: `platforms`, `beatmap_defaults`, `sound_design`,
  `hook_strategy`, `intro_strategy`.
- Existing `layout_mode`, `motion_engine`, and `caption_preset` values remain
  valid.

## Workflows

Workflows are new. Bootstrap copies the five seeds into
`<workspace>/.opencode/workflows/`. Existing workspaces without workflows keep
working; AGENTS.md will show an empty workflow list until bootstrap/sync runs.

## MCP

- The default profile is `opencode`.
- Prompts are disabled by default.
- Recipes are not available through MCP in any profile.
- Use `vf_catalog_search` / `vf://docs/steps` and `vf_exec(action="step")`.

## Exports

Canonical v3 names:

```text
youtube_master.mp4
resolve_timeline.fcpxml
premiere_timeline.xml
kdenlive_project.mlt
```

Legacy names (`final_youtube.mp4`, `timeline_resolve.fcpxml`, etc.) are still
accepted by validation during migration.

## Verification

```bash
uv sync --extra dev --extra vision --extra faster-whisper --extra tray
uv run pytest tests/unit tests/contract
./scripts/gate_local.sh --full
```
