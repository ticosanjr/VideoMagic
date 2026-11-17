# OpenCode workspace bootstrap

VideoFlow can generate a complete OpenCode workspace wired to its MCP servers,
with the style catalog copied into `presets/`.

## UI

`Setup → Connect → OpenCode Studio Bootstrap` offers:

- folder picker for `target_dir`;
- MCP profile dropdown;
- live preview of `presets/*.md` styles that will be copied;
- checkboxes for global config, overwrite, 10s sample project, allowed root and prompts;
- result with created files, copied styles, warnings and a copyable launch command.

## CLI

```bash
videoflow init-opencode /path/to/workspace --profile full
videoflow init-opencode /path/to/workspace --profile core --with-sample
videoflow init-opencode /path/to/workspace --global --overwrite
```

Options:

| Flag | Meaning |
| --- | --- |
| `--profile` | `core`, `decupagem`, `broll`, `audio`, `vision`, `full` |
| `--global` | merge VideoFlow servers into `~/.config/opencode/opencode.json` |
| `--overwrite` | replace existing skills/commands/preset files |
| `--with-sample` | generate a 10s sample project |
| `--no-register-root` | do not add the target to `paths.allowed_roots` |
| `--no-prompts` | omit the VideoFlow MCP prompts |

## REST

```text
POST /api/v1/system/bootstrap/opencode
```

```json
{
  "target_dir": "/path/to/workspace",
  "mcp_profile": "full",
  "register_global_opencode": false,
  "overwrite": false,
  "include_sample_project": false,
  "register_root": true,
  "prompts": true
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
│   └── commands/{decupar,beatmap,salvar-estilo,exportar}.md
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
4. Generate/update `AGENTS.md` with the mandatory style-selection protocol.
5. Copy skills and slash commands.
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

