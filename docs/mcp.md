# MCP server — agent profile

VideoFlow 3.7.0 exposes a **34-tool core MCP** plus four isolated domain servers:

```text
mcp-vf-core      34 tools   project, styles, jobs, timeline, scenes, export, ingest, QA, GPU, transcript
mcp-vf-media-fetch  4 tools stock B-roll, images, URL segments, SFX
mcp-vf-audio-studio 5 tools TTS, cleanup, stems, music/SFX, mix
mcp-vf-vision-fx    6 tools word-aligned captions, rembg, upscale, motion, Ken Burns, screen/browser capture
```

The core intentionally does not expose the old 82-tool UI CRUD surface. Node
schemas are loaded on demand through resources. **Recipes are not exposed via
MCP**: agents see the step catalog and run individual steps, while UI, CLI, and
REST keep the recipe engine.

## Transports

| Transport | Command or URL |
| --- | --- |
| stdio | `uv run videoflow-mcp` |
| Streamable HTTP | `http://127.0.0.1:8765/mcp/` |
| Headless daemon | `videoflow serve --mcp-only --port 8765` |

The server stays on loopback. The stdio process inherits the path allowlist and
does not start a second API. Packaged builds also expose the domain servers as
`videoflow mcp-fetch`, `videoflow mcp-audio`, and `videoflow mcp-vision`.

## Workspace and automatic MCP install

Setup → Workspace chooses a folder, registers it as an allowed root, copies
styles and workflows, and merges the VideoFlow MCP server into the OpenCode
config with a backup. Setup → Styles, Formats, and Help expose the style
catalog, aspect ratios/safe zones, and MCP workflow instructions.

## Projects

Every project-scoped tool requires an explicit `project_id`. There is no
process-global "current project" fallback.

```text
vf_project(action="init", output="/projects/interview", sources=["/media/a.mp4"])
```

The call returns a stable `project_id`, the project record, the state summary,
and resource links. `project_id` may be a slug; pass it without `output` to use
`$VF_WORKSPACE_ROOT/projects/{project_id}`. The canonical `project_state.json`
now carries a `pipeline`
block with transcript, selected Shorts, captions, analysis spans, artifacts,
metadata, time map, and step checkpoints; `projects/{id}/state.json` mirrors it. Multiple sub-agents can work on different projects in
parallel. Writes to the same project are serialized by a project lock and
`vf_edit_timeline` supports `expected_revision` for conflict detection.

## Core tools (34)

### Project, catalog, and execution

| Tool | Purpose |
| --- | --- |
| `vf_style` | `list`, `get`, `save`, `sync`, `analyze`, `delete`, or `learn_rule` for Markdown styles. |
| `vf_style_validate` | Validate presets, layouts, engines, and fonts. |
| `vf_style_apply` | Compile style params, a beat-map draft, and a revision diff. |
| `vf_project` | Init/open/status, list, clone, archive, delete, and revision undo/history/restore. |
| `vf_capabilities` | Backends, models, GPU worker, and external policy. |
| `vf_catalog_search` | List or search node/tool types with pagination. |
| `vf_exec` | Run one catalog step or edit a Short. Recipes are not exposed. |
| `vf_run` | Run an ordered, linear chain of steps with persisted checkpoints. |

### Jobs, timeline, artifacts

| Tool | Purpose |
| --- | --- |
| `vf_job` | `list`, `status`, `get`, `wait`, `cancel`, `logs`, or `qa` for a job. |
| `vf_timeline` | Read, edit, or `apply_beatmap` the canonical timeline. |
| `vf_beatmap_plan` | Generate a structured beat-map draft from transcript + style. |
| `vf_overlay` | Insert an image/video overlay by source or timeline time. |
| `vf_overlay_preview` | Render overlay boxes or `action="crop"` with the normalized crop box and thirds grid. |
| `vf_layout` | Auto-pack overlay margins and write `layout.json`. |
| `vf_caption_preview` | Render before/during/after frames for the active caption. |
| `vf_qa_autofix` | Resolve overlay/caption collisions, persist the layout, and optionally re-render from the segment cache. |
| `vf_depth_composite` | Cut one range, matte the presenter, and stack a graphic at `z=10` behind it at `z=20`. |
| `vf_pip` | Add a rounded-window picture-in-picture overlay with a cached alpha mask. |
| `vf_parallax` | Split a still into background and subject layers and animate 2.5D parallax. |
| `vf_style_preview` | Render a short style card with palette, font, layout, and caption. |
| `vf_artifact` | List or read artifacts, including image content. |
| `vf_transcript_query` | Search or page the cleaned transcript without dumping it. |
| `vf_glossary` | List, update, or apply channel glossary terms. |
| `vf_storyboard_strip` | Render one contact-sheet PNG for a timeline or source range. |
| `vf_qa_compare` | Compare two immutable QA reports for regressions. |

### Delivery and operations

| Tool | Purpose |
| --- | --- |
| `vf_export` | `bundle`, `render`, `validate`, or `roundtrip`; canonical master plus `resolve`, `premiere`, and `kdenlive`. |
| `vf_shorts_batch` | Render multiple Shorts with per-clip style, crop, intro, and music. |
| `vf_scenes` | `analyze`, `manifest`, `keyframe`, `supercontext`, or `cache` for the scene-intelligence layer. |
| `vf_qa_final` | Audit the delivered MP4, loudness, silence, safe zones, captions, word fidelity, contact sheet, and waveform. |
| `vf_assets` | List assets, licenses, or fonts; approve, quarantine, or register fonts. |
| `vf_interaction` | List/read/answer HITL requests, including curation previews. |
| `vf_ingest` | Session ingest or multicam synchronization. |
| `vf_preflight_plan` | Validate schema, dependencies, licenses, disk, GPU, and cost. |
| `vf_gpu_preflight` | Validate the Windows GPU worker before a long job. |

### Hybrid compute

`vf_capabilities` reports a top-level `compute` object and a `compute_router`
manifest entry with the active placement, worker identity, GPU/VRAM telemetry,
and remote capabilities. `VF_COMPUTE_MODE=local_only` guarantees no network
I/O. See [gpu-worker.md](gpu-worker.md).

### Stateful runs and the shared queue

`vf_run` accepts an ordered, linear list of step types or a workflow id whose
nodes are all catalog steps. It shares one `PipelineContext`, writes a
checkpoint after every step, and supports `through`, `resume`, and `wait`.

```text
vf_run(project_id="p1", steps=["ingest", "transcribe", "edit.timeline"], wait=True)
```

`vf_job(action="list")` reads the shared SQLite queue used by MCP, REST, and the
tray. Cancels are written as a `cancel_requested` flag and picked up by the
worker heartbeat.

Optionally, when the user did not choose another destination, run
`vf_exec(action="step", step_id="delivery.collect", params={"mode":"copy"})`
to consolidate final videos and exports under
`VideoFlow_Output/{videos,exports,shorts,scenes}` at the workspace root. This is
a delivery convenience only: the MCP accepts any output path and never blocks or
degrades a job because artifacts live elsewhere.
Heavy ASR, alignment, matte, scene analysis, and Short render should use
`compute_policy="auto"` or `"remote"` when a Windows worker is configured; local
fallback must report `degraded=true`.

`vf_export` is the canonical delivery entry point. Its MP4 uses the same
`master_export` path as `export.video` and the bundle (same grade, LUT, grain,
overlays, captions, and audio), and delivery sidecars are PCM 24-bit. The social
master defaults to `fps=30`; pass `fps="source"` to preserve the source cadence.
`qa_mode="fast"` validates duration/frames, edge silence, and overlay bounds
without WER or contact sheets; `qa_mode="full"` dispatches a background QA job;
`qa_mode="off"` skips export QA.

`vf_project` also supports `list`, `clone`, `archive`, `unarchive`, `delete`,
`history`, `undo`, and `restore`. Deleting a non-empty output requires
`force=true`.

## Domain servers

The domain servers use the same workspace contract and can be enabled per
OpenCode profile:

```bash
scripts/install_mcp_servers.sh
uv run python scripts/generate_mcp_config.py --profile full > mcp.json
```

Profiles: `core`, `decupagem`, `broll`, `audio`, `vision`, `full`.

Pass `--no-prompts` (or `VF_MCP_PROMPTS=0`) to omit the three
`videoflow_produce/review/deliver` prompts when channel `AGENTS.md` instructions
are authoritative.

Every domain asset is written under:

```text
$VF_WORKSPACE_ROOT/projects/{project_id}/assets/{voice,broll,images,sfx,music,graphics}/
```

and gets a `.meta.json` sidecar with source, license, checksum and media
metadata. A deterministic `params_hash` makes downloads and generations
idempotent.

## GPU worker and ComputeRouter

The Windows worker is optional. The allowlisted handlers are `tts`, `music`,
`sfx`, `stems`, `upscale`, `comfyui`, `asr`, and `diarize`. The router chooses
remote only when the worker is healthy, advertises the capability, has enough
VRAM and queue capacity:

```text
VF_COMPUTE_MODE=auto|local_only|remote_preferred
VF_GPU_WORKER_URL=http://windows-host:8766
VF_GPU_WORKER_TOKEN=...
```

`local_only` never performs network I/O. `auto` falls back to the local
CPU/Vulkan implementation with a structured reason: Faster-Whisper or
whisper.cpp Vulkan for `asr`, and the local `audio.diarize` step for `diarize`.

The worker exposes `/health`, content-addressed `/artifacts`, async
`/jobs/{capability}`, status and artifact download endpoints, token auth,
VRAM/model TTL and an allowlisted handler registry. `scripts/gpu_worker_smoke.py
--local` starts the real worker app on loopback with deterministic handlers to
exercise upload, ASR, upscale, and local fallback; the same script with `--url`
runs the manual Windows GPU smoke.

## Delivery bundle

One call writes the social master and every NLE from the same validated
timeline:

```text
vf_export(project_id="...", targets="all")
```

Targets accept `mp4_youtube`, `resolve`, `premiere`, `kdenlive`, `edl`, and
`all`. The MP4 uses H.264 High, AAC 320 kbps, CFR, `+faststart`, and a
`-16.5 LUFS` / `-1.0 dBTP` target when no mastered `audio/master.wav` exists.
The manifest lands in `exports/bundle.json` with SHA-256 per artifact and
media/duration/license validation for every export. Fixed names are
`youtube_master.mp4`, `resolve_timeline.fcpxml`, `premiere_timeline.xml`,
`kdenlive_project.kdenlive`, and `kdenlive_project.mlt`.

When `targets` is omitted, the project's bound style supplies
`export_targets`. Pass an explicit target list to override it.

```text
vf_export(action="validate", project_id="...")
vf_export(action="roundtrip", project_id="...", nle="premiere", path="...")
```

`roundtrip` accepts `fcpxml`, `xmeml`/`premiere`, `mlt`/`kdenlive`, and
`resolve`. After a transcript shift, long-form captions are regenerated in
`captions/captions.ass`, `captions/captions.srt`, and `subtitles.ass`; ducking
levels are written to `audio/ducking.json`. Manual clip timing edits without
`vf:` markers also shift transcript and existing ducking ranges.

Captions are exported as their own track: FCPXML lane 6, a second XMEML video
track, and Kdenlive `playlist_captions`.

## Declarative timeline edits

`clone_style` samples screenshots, video frames, and measured cut rhythm from a
reference URL or directory; `learn_rule` merges notes and caps the rulebook at
15 active rules.

```text
vf_timeline(action="apply_beatmap", project_id="...", expected_revision=3,
            beatmap={"revision": 3, "cuts": [...], "broll": [...],
                     "overlays": [...], "zoom_keyframes": [...],
                     "sfx_events": [...], "music_tracks": [...]})
```

The manifest is validated against a project copy and saved once. Missing or
license-blocked assets reject the whole edit.

## Async render contract

```text
vf_export(action="render") -> job_id
vf_job(action="wait")      -> final result, duration, resolution, LUFS, QA status
vf_artifact(action="get")  -> path, checksum, resource link, image content
```

Rendering never blocks a tool call. `vf_job(action="wait")` reports progress
through the MCP context and returns a typed `timeout` result when the deadline
expires.

## Resources

```text
vf://projects
vf://projects/{project_id}/state
vf://projects/{project_id}/timeline
vf://projects/{project_id}/transcript
vf://projects/{project_id}/jobs
vf://projects/{project_id}/artifacts
vf://projects/{project_id}/scenes
vf://projects/{project_id}/scenes/{scene_id}/keyframe
vf://projects/{project_id}/jobs/{job_id}/logs
vf://styles
vf://styles/{style_id}
vf://presets/{channel_id}/rulebook
vf://presets/{channel_id}/kit
vf://docs/steps
vf://docs/steps/{step_type}
vf://docs/contracts/{name}
```

`vf://docs/steps` lists every node/tool type; `vf://docs/steps/{step_type}`
returns its full parameter schema; `vf://docs/contracts/{name}` returns one
short media/QA contract from `docs/contracts/`.

Resources are read-only. Tools perform writes.

## Channel kits and hard constraints

`vf_project(action="init", channel_id="youtube-talking-head")` binds a project to
a shipped channel kit. `<code>style_id</code>` is separate and must reference a
Markdown style; passing a style id as `channel_id` returns
`channel_not_found`. Recipe execution (UI/CLI/REST) merges channel kit defaults
and inviolable hard constraints (aspect ratio, caption preset, LUT, B-roll
style). Learned rules are capped at 15 and consolidated by
`preset.compile_rule`.

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

The decupagem acoustic phase adds `audio.events` (YAMNet or heuristic/AST) and
an `audio.vad` RMS map. See [decupage.md](decupage.md).

`session.cull` applies retake discards to the existing multi-source timeline
without rebuilding it, including retakes that span file boundaries.

`sync.multicam_audio` extracts 16 kHz mono PCM, runs normalized cross-correlation,
reports offset/drift/confidence, and can store a source offset when confidence
crosses the threshold. With `compose="pip"` it also adds the secondary source as
a timed picture-in-picture overlay for facecam + screen compositions.

The MP4 exporter renders each segment from its own source and the FCPXML/XMEML
writers emit one asset per source. Kdenlive/MLT remains a static export.

## Observability

`vf_job(action="logs")` returns:

- stage timings and status;
- bounded logs and FFmpeg command lines;
- peak process RSS;
- a `log_resource` for the persisted job log.

`vf_job(action="qa")` returns defects with frame paths and artifact ids. With
`include_images=true`, frames are also returned as MCP image content so a VLM
can inspect the failed frame.

## NLE roundtrip

`vf_export(action="roundtrip")` supports:

- `direction=push`: write FCPXML and import it into the NLE;
- `direction=pull`: read external cuts/markers;
- `direction=sync`: apply `nle.sync_back`.

`nle=resolve` uses the optional DaVinci Resolve Studio scripting bridge. The
bridge is capability-detected at runtime and falls back to static FCPXML when
Resolve or external scripting is unavailable.

## Agent flow

```text
1. vf_project(action="init")
2. vf_capabilities / vf_catalog_search
3. vf_ingest(action="session") (optional)
4. vf_catalog_search / vf://docs/steps -> choose nodes
5. vf_exec(action="step", step_id=..., params=...) for each node
6. vf_job(action="wait")
7. vf_job(action="logs") / vf_job(action="qa")
8. vf_timeline(action="get|edit")
9. vf_export(action="render") -> vf_job(action="wait")
10. vf_artifact(action="get")
11. vf_export(action="bundle|roundtrip|validate")
```
