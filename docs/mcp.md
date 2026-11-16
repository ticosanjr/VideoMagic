# MCP server — agent profile

VideoFlow 2.85 exposes a **project-scoped, 22-tool MCP surface** for OpenCode and
similar agents. The server is built on the official Python SDK v2.

The agent profile intentionally does not expose the legacy 82-tool UI CRUD
surface. Step and recipe schemas are loaded on demand through resources.

## Transports

| Transport | Command or URL |
| --- | --- |
| stdio | `uv run videoflow-mcp` |
| Streamable HTTP | `http://127.0.0.1:8765/mcp/` |
| Headless daemon | `videoflow serve --mcp-only --port 8765` |

The server stays on loopback. The stdio process inherits the path allowlist and
does not start a second API.

## Projects

Every project-scoped tool requires an explicit `project_id`. There is no
process-global "current project" fallback.

```text
vf_project_init(output="/projects/interview", sources=["/media/a.mp4"])
```

The call returns a stable `project_id`, the project record, the state summary,
and resource links. Multiple sub-agents can work on different projects in
parallel. Writes to the same project are serialized by a project lock and
`vf_edit_timeline` supports `expected_revision` for conflict detection.

## Tools (22)

### Project and system

| Tool | Purpose |
| --- | --- |
| `vf_project_init` | Create or adopt a project and probe source files. |
| `vf_project_status` | State, jobs, artifacts, and resource links. |
| `vf_capabilities` | Backend, model, and external-provider availability. |

### Recipes

| Tool | Purpose |
| --- | --- |
| `vf_list_recipes` | List built-in recipes. |
| `vf_get_recipe` | Return one recipe document. |
| `vf_validate_recipe` | Validate a named or inline recipe DAG. |
| `vf_run_recipe` | Run a named or inline recipe in one project. |

### Jobs and observability

| Tool | Purpose |
| --- | --- |
| `vf_get_job` | Job status, artifacts, and QA summary. |
| `vf_wait_job` | Bounded wait with MCP progress notifications. |
| `vf_get_step_logs` | Logs, commands, stages, timing, and peak RSS. |
| `vf_get_qa_artifacts` | QA defects, frame paths, and optional image content. |

### Timeline and transcript

| Tool | Purpose |
| --- | --- |
| `vf_get_timeline` | Timeline with per-clip `source_id`. |
| `vf_edit_timeline` | Trim, move, split, delete, or ripple with revision checks. |
| `vf_get_transcript` | Structured transcript and SRT. |

### Artifacts and Shorts

| Tool | Purpose |
| --- | --- |
| `vf_get_artifact` | Manifest, checksum, path, and image content. |
| `vf_edit_short` | Trim, retitle, reframe, and re-render one Short. |

### Ingest and multicam

| Tool | Purpose |
| --- | --- |
| `vf_ingest_session` | Order and normalize a multi-take recording session. |
| `vf_sync_multicam` | Audio cross-correlation offset, drift, and confidence. |

### Render and delivery

| Tool | Purpose |
| --- | --- |
| `vf_render_start` | Start a timeline or preview render job. |
| `vf_nle_roundtrip` | Push/pull cuts and markers through FCPXML/MLT or Resolve. |
| `vf_validate_exports` | Validate FCPXML, XMEML, and Kdenlive artifacts. |
| `vf_respond_interaction` | Answer a HITL request and resume the job. |

## Async render contract

```text
vf_render_start -> job_id
vf_wait_job     -> final result, duration, resolution, LUFS, QA status
vf_get_artifact -> path, checksum, resource link, image content
```

Rendering never blocks a tool call. `vf_wait_job` reports progress through the
MCP context and returns a typed `timeout` result when the deadline expires.

## Resources

```text
vf://projects
vf://projects/{project_id}/state
vf://projects/{project_id}/timeline
vf://projects/{project_id}/transcript
vf://projects/{project_id}/jobs
vf://projects/{project_id}/artifacts
vf://projects/{project_id}/jobs/{job_id}/logs
vf://presets/{channel_id}/rulebook
vf://presets/{channel_id}/kit
vf://docs/steps/{step_type}
vf://docs/recipes/{recipe_id}
```

Resources are read-only. Tools perform writes.

## Channel kits and hard constraints

`vf_project_init(channel_id="canal-rafael")` binds a project to a channel
rulebook. `vf_run_recipe` merges the channel kit defaults into the recipe and
then applies inviolable hard constraints (aspect ratio, caption preset, LUT,
B-roll style). Explicit recipe parameters cannot override a hard constraint.
Learned rules are capped at 15 and consolidated by `preset.compile_rule`.

## Multi-source projects

`ProjectState` carries `sources`, `primary_source_id`, `source_offsets`, and
`source_id` on every video/audio segment. `session.ingest`:

1. discovers files from an explicit list or `raw_dir`;
2. orders by name, mtime, timecode, or automatic;
3. probes every clip;
4. normalizes mismatched CFR/resolution/audio when needed;
5. keeps each normalized file as a real source;
6. builds a packed multi-source timeline and a concatenated session audio file
   for transcription.

`session.cull` applies retake discards to the existing multi-source timeline
without rebuilding it, including retakes that span file boundaries.

`sync.multicam_audio` extracts 16 kHz mono PCM, runs normalized cross-correlation,
reports offset/drift/confidence, and can store a source offset when confidence
crosses the threshold. With `compose="pip"` it also adds the secondary source as
a timed picture-in-picture overlay for facecam + screen compositions.

The MP4 exporter renders each segment from its own source and the FCPXML/XMEML
writers emit one asset per source. Kdenlive/MLT remains a static export.

## Observability

`vf_get_step_logs` returns:

- stage timings and status;
- bounded logs and FFmpeg command lines;
- peak process RSS;
- a `log_resource` for the persisted job log.

`vf_get_qa_artifacts` returns defects with frame paths and artifact ids. With
`include_images=true`, frames are also returned as MCP image content so a VLM
can inspect the failed frame.

## NLE roundtrip

`vf_nle_roundtrip` supports:

- `direction=push`: write FCPXML and import it into the NLE;
- `direction=pull`: read external cuts/markers;
- `direction=sync`: apply `nle.sync_back`.

`nle=resolve` uses the optional DaVinci Resolve Studio scripting bridge. The
bridge is capability-detected at runtime and falls back to static FCPXML when
Resolve or external scripting is unavailable.

## Agent flow

```text
1. vf_project_init
2. vf_capabilities / vf_list_recipes
3. vf_ingest_session (optional)
4. vf_run_recipe
5. vf_wait_job
6. vf_get_step_logs / vf_get_qa_artifacts
7. vf_get_timeline / vf_edit_timeline
8. vf_render_start -> vf_wait_job
9. vf_get_artifact
10. vf_nle_roundtrip / vf_validate_exports
```
