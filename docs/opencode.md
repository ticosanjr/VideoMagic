# OpenCode workspace bootstrap

VideoFlow can generate a complete OpenCode workspace wired to its MCP servers,
with the style catalog copied into `presets/` and workflows into
`.opencode/workflows/`.

## UI

`Setup → Connect` contains the **OpenCode Studio Bootstrap** and the
**OpenCode Studio Manager**:

- `AGENTS.md` tab: edit, preview and restore the Diretor Lego protocol.
- `Workflows` tab: list, open, create, edit, duplicate, restore and delete
  playbooks.
- `Styles` tab: edit the frontmatter/body of all 18 catalog styles.

The Bootstrap offers:

- folder picker for `target_dir`;
- `opencode` MCP profile by default;
- workflow checkboxes;
- live preview of styles that will be copied;
- workspace-local config by default (no global edits);
- overwrite, sample project, allowed root and prompt options;
- MCP health (global entries, stable launcher, worker URL seen by MCP);
- “Remove global VideoFlow MCP” cleanup;
- result with created files, workflows, styles, warnings and launch command.

## CLI

```bash
videoflow init-opencode /path/to/workspace
videoflow init-opencode /path/to/workspace --profile opencode
videoflow init-opencode /path/to/workspace --profile core --with-sample
videoflow init-opencode /path/to/workspace --global --overwrite
```

Options:

| Flag | Meaning |
| --- | --- |
| `--profile` | `opencode` (default), `core`, `decupagem`, `broll`, `audio`, `vision`, `full` |
| `--global` | opt in to merging VideoFlow servers into `~/.config/opencode/opencode.json` |
| `--cleanup-global` | remove only VideoFlow MCP entries from the global config |
| `--overwrite` | replace existing skills/commands/preset files |
| `--with-sample` | generate a 10s sample project |
| `--no-register-root` | do not add the target to `paths.allowed_roots` |
| `--no-prompts` | omit the VideoFlow MCP prompts (default) |
| `--prompts` | enable the generic MCP prompts |

## REST

```text
POST /api/v1/system/bootstrap/opencode
```

```json
{
  "target_dir": "/path/to/workspace",
  "mcp_profile": "opencode",
  "register_global_opencode": false,
  "overwrite": false,
  "include_sample_project": false,
  "register_root": true,
  "prompts": false,
  "workflow_ids": ["youtube-longform", "reels-from-raw"]
}
```

Response:

```json
{
  "ok": true,
  "status": "ok",
  "target_dir": "/path/to/workspace",
  "created_files": ["..."],
  "skipped_files": [],
  "copied_styles": ["canal-paula-reels"],
  "copied_workflows": ["youtube-longform", "reels-from-raw"],
  "mcp_servers": ["audio", "core", "fetch", "vision"],
  "launch_command": "cd \"/path/to/workspace\" && opencode"
}
```

## Generated tree

```text
workspace/
├── opencode.json
├── AGENTS.md
├── .opencode/
│   ├── skills/video-longform.md
│   ├── skills/video-shorts.md
│   ├── skills/video-clone-style.md
│   ├── workflows/*.md
│   └── commands/{decupar,beatmap,salvar-estilo,exportar,editar-longo,editar-reels,cortar-shorts}.md
├── presets/*.md
├── references/
└── projects/
```

`AGENTS.md` keeps a managed block between
`<!-- videoflow:opencode:start -->` and
`<!-- videoflow:opencode:end -->`; user text outside the block is preserved.

`opencode.json` merges VideoFlow server entries into an existing file without
removing other servers or top-level settings. Existing files are backed up
before changes. JSONC files with comments are left untouched unless
`overwrite=true`.

## Bootstrap behavior

1. Resolve and create the target directory.
2. Optionally register it in `paths.allowed_roots`.
3. Create directories and `opencode.json`.
4. Generate/update `AGENTS.md` with the mandatory Style + Workflow selection protocol.
5. Copy skills, commands and selected workflows.
6. Sync the Markdown style catalog into `presets/`.
7. Optionally generate the 10s sample project.
8. Return `launch_command`.

Secrets are never written to disk: the generated config uses
`${VF_GPU_WORKER_TOKEN:-}` and related environment references.

## Packaged MCP servers

The portable binary/AppImage embeds the core and the three domain servers:

```text
videoflow mcp          # core
videoflow mcp-fetch    # stock media
videoflow mcp-audio    # TTS, stems, music, mix
videoflow mcp-vision   # ASR, mattes, upscale, motion, capture
```

`init-opencode` detects a packaged build and writes those subcommands instead
of `uv run` paths, so the `full` profile works without a source checkout.

## Local-only install and shared worker state

The default is workspace-local: `<workspace>/opencode.json`. VideoFlow only
edits the global OpenCode config when `--global` or
`register_global_opencode=true` is explicit.

Generated MCP environments do **not** override `VIDEOWFLOW_HOME`. The core and
domain servers therefore read the same `settings.json`, `gpu.json`, secrets,
and worker token as the UI. `VF_WORKSPACE_ROOT` remains workspace-specific.

Packaged builds use a stable launcher (`~/.local/share/videoflow/bin/videoflow`
on Linux or `%LOCALAPPDATA%\VideoFlow\videoflow-mcp.cmd` on Windows) instead
of the disposable AppImage `/tmp/.mount_*` path. The launcher is refreshed when
the app starts.

Generated configs set:

```json
"mcp": {
  "timeout": {
    "startup": 120000,
    "catalog": 120000
  }
}
```

This avoids OpenCode's 30-second default timing out while a packaged server
warms up.

## Health and cleanup

```text
GET  /api/v1/system/opencode/mcp-health
POST /api/v1/system/opencode/cleanup-global
```

The health route reports the global config path, VideoFlow entries, launcher,
worker URL seen by MCP, and stale-path warnings. Cleanup removes only entries
named `core`, `fetch`, `audio`, or `vision` whose command references VideoFlow;
unrelated MCP servers are preserved and the file is backed up.

