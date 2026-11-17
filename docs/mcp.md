# MCP server — agent profile

VideoFlow 2.91 exposes a **13-tool core MCP** plus four isolated domain servers:

```text
mcp-vf-core      13 tools   project, styles, jobs, timeline, render, exports, ingest
mcp-vf-media-fetch  4 tools stock B-roll, images, URL segments, SFX
mcp-vf-audio-studio 5 tools TTS, cleanup, stems, music/SFX, mix
mcp-vf-vision-fx    6 tools word-aligned captions, rembg, upscale, motion, Ken Burns, screen/browser capture
```

The core intentionally does not expose the old 82-tool UI CRUD surface. Step
and recipe schemas are loaded on demand through resources.

## Transports

| Transport | Command or URL |
| --- | --- |
| stdio | `uv run videoflow-mcp` |
| Streamable HTTP | `http://127.0.0.1:8765/mcp/` |
| Headless daemon | `videoflow serve --mcp-only --port 8765` |

The server stays on loopback. The stdio process inherits the path allowlist and
does not start a second API. Packaged builds also expose the domain servers as
`videoflow mcp-fetch`, `videoflow mcp-audio`, and `videoflow mcp-vision`.

## Projects

Every project-scoped tool requires an explicit `project_id`. There is no
process-global "current project" fallback.

```text
vf_project(action="init", output="/projects/interview", sources=["/media/a.mp4"])
```

The call returns a stable `project_id`, the project record, the state summary,
and resource links. Multiple sub-agents can work on different projects in
parallel. Writes to the same project are serialized by a project lock and
`vf_edit_timeline` supports `expected_revision` for conflict detection.

## Core tools (13)

### Project, catalog, and execution

| Tool | Purpose |
| --- | --- |
| `vf_style` | List/save/sync Markdown styles and learn review rules. |
| `vf_project` | Create/open/status a project; `clone_style` and `learn_rule`. |
| `vf_capabilities` | Backends, models, GPU worker, and external policy. |
| `vf_catalog_search` | Search steps/recipes without loading schemas. |
| `vf_exec` | Run a recipe, a Short edit, or one internal catalog step. |

### Jobs, timeline, artifacts

| Tool | Purpose |
| --- | --- |
| `vf_job` | Get/wait/logs/QA for a job. |
| `vf_timeline` | Read, edit, or `apply_beatmap` the canonical timeline. |
| `vf_artifact` | List or read artifacts, including image content. |

### Delivery and operations

| Tool | Purpose |
| --- | --- |
| `vf_render` | Start/inspect/cancel a render job. |
| `vf_exports` | `bundle`, `validate`, or `roundtrip` for every NLE. |
| `vf_interaction` | List/read/answer HITL requests. |
| `vf_ingest` | Session ingest or multicam synchronization. |
| `vf_qa` | Read QA artifacts or route new QA through `vf_exec`. |

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
vf_exports(action="bundle", project_id="...", targets="all")
```

Targets accept `mp4_youtube`, `resolve`, `premiere`, `kdenlive`, `edl`, and
`all`. The MP4 uses H.264 High, AAC 320 kbps, CFR, `+faststart`, and a
`-16.5 LUFS` / `-1.0 dBTP` target when no mastered `audio/master.wav` exists.
The manifest lands in `exports/bundle.json` with SHA-256 per artifact and
media/duration/license validation for every export. Fixed names are
`final_youtube.mp4`, `timeline_resolve.fcpxml`, `timeline_premiere.xml`,
`timeline_kdenlive.kdenlive`, and `timeline_kdenlive.mlt`.

When `targets` is omitted, the project's bound style supplies
`export_targets`. Pass an explicit target list to override it.

```text
vf_exports(action="validate", project_id="...")
vf_exports(action="roundtrip", project_id="...", nle="premiere", path="...")
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
vf://styles
vf://styles/{style_id}
vf://presets/{channel_id}/rulebook
vf://presets/{channel_id}/kit
vf://docs/steps/{step_type}
vf://docs/recipes/{recipe_id}
```

Resources are read-only. Tools perform writes.

## Channel kits and hard constraints

`vf_project(action="init", channel_id="canal-rafael")` binds a project to a channel
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

`vf_job(action="logs")` returns:

- stage timings and status;
- bounded logs and FFmpeg command lines;
- peak process RSS;
- a `log_resource` for the persisted job log.

`vf_qa(action="artifacts")` returns defects with frame paths and artifact ids. With
`include_images=true`, frames are also returned as MCP image content so a VLM
can inspect the failed frame.

## NLE roundtrip

`vf_exports(action="roundtrip")` supports:

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
4. vf_exec(action="recipe")
5. vf_job(action="wait")
6. vf_job(action="logs") / vf_qa(action="artifacts")
7. vf_timeline(action="get|edit")
8. vf_render(action="start") -> vf_job(action="wait")
9. vf_artifact(action="get")
10. vf_exports(action="roundtrip|validate")
```
