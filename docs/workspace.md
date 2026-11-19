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

`project_id` accepts a human-readable slug (for example `meu-documentario`) as
well as a UUID. The registry key and workspace folder keep the slug, while the
internal `ProjectState.project_id` is a deterministic UUID derived from it, so
re-running init or clone for the same slug is stable. `vf_project_init` can
create a project from `project_id` alone; the output defaults to
`$VF_WORKSPACE_ROOT/projects/{project_id}`.

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
- Export gates only assets referenced by the current timeline; unrelated ledger
  entries are reported but do not block delivery.
- Absolute paths and traversal outside the project are rejected.
- The core mirrors the project state into `state.json`; API/UI keep their
  existing output path for compatibility.
- `project_state.json` is canonical. Its `pipeline` block persists the
  tools-only context: transcript, selected Shorts, captions, analysis spans,
  artifacts, metadata, `time_map`, and step checkpoints. `state.json` mirrors
  the same document.
- Extracted PCM and normalized proxies are hardlinked into
  `{VF_WORKSPACE_ROOT}/_pool/{sha256}/` when the filesystem supports it.
- `VF_CACHE_DIR` (or `paths.cache_dir`) holds analysis, rounded masks, and
  throwaway render caches; validated deliveries prune segment caches.

Domain servers use only `vf_contracts` and never import the core package.
