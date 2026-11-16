# Shared workspace contract

VideoFlow 2.90 separates the core from domain MCP servers through a filesystem
contract. The root is configurable:

```bash
export VF_WORKSPACE_ROOT="$HOME/VideoFlow/workspace"
```

When `VF_WORKSPACE_ROOT` is unset, `VIDEOWFLOW_HOME/workspace` is used, or
`~/.videoflow/workspace` as the final default.

```text
$VF_WORKSPACE_ROOT/projects/{project_id}/
├── project.json
├── state.json
├── script/
├── assets/
│   ├── voice/
│   ├── broll/
│   ├── images/
│   ├── sfx/
│   ├── music/
│   └── graphics/
├── captions/
└── renders/{drafts,final,manifests}/
```

`project.json` records `workspace_version`, `project_id`, `name`, `channel_id`,
`output`, `sources`, `primary_source`, `state_path`, `revision`, and
`schema_version`.

Every asset is content-addressed and has a `.meta.json` sidecar:

```json
{
  "asset_id": "...",
  "project_id": "...",
  "kind": "broll",
  "path": "assets/broll/<sha>.mp4",
  "source": "pexels",
  "license": "pexels",
  "attribution_required": false,
  "sha256": "...",
  "params_hash": "...",
  "duration_sec": 4.0,
  "width": 1920,
  "height": 1080
}
```

- `params_hash` makes downloads and generations idempotent.
- `unknown` and unapproved `youtube_fair_use` assets block export.
- Absolute paths and traversal outside the project are rejected.
- The core mirrors the project state into `state.json`; API/UI keep their
  existing output path for compatibility.

Domain servers use only `vf_contracts` and never import the core package.
