# VideoFlow documentation

Everything here is English. The original Portuguese brief is archived and
non-normative at [origin/prd-pt.md](origin/prd-pt.md).

## Implementation status (0.44.0)

| Area | State |
| --- | --- |
| Rational time, state, cache, planning, retake guard, path jail | implemented |
| FFmpeg ingest and PCM fingerprint | implemented |
| Silero VAD via ONNX Runtime with FFmpeg `silencedetect` fallback | implemented |
| Deterministic timeline, J/L-cuts, fades, punch-ins | implemented |
| FCPXML 1.9/1.10, xmeml v4, native Kdenlive MLT export | implemented |
| Portable artifacts | 0.44.0 lean Linux binary and AppImage; speech weights are optional downloads from the Models tab |
| Run history | persisted in `work/run-history.json`, including failed runs, exposed by `GET /api/v1/runs` |
| Diagnostics | `work/failure.json` includes stage, error, FFmpeg command, stderr, and log tail |
| NLE validation | `scripts/validate_nle.py` and `POST /api/v1/exports/validate` |
| Schema gates | recipe and project-state `schema_version` migration |
| Maintenance | `POST /api/v1/maintenance/prune`, `videoflow recipe cache prune`, and opt-out post-run pruning |
| Release | tag-triggered Linux/AppImage/Windows/SBOM release workflow |
| Batch persistence | JSON batch history under the VideoFlow home, reloaded after restart |
| Job persistence | job JSON under the VideoFlow home; interrupted jobs fail safely on restart |
| Batch resume | resume failed/cancelled batches and skip completed items |
| Preview | inline MP4 artifact and Short previews served through the job API |
| MLT smoke | optional `melt` render check for generated Kdenlive projects |
| Recipe UI | inline node fields, schema validation, saved layout, per-step progress, NLE validation modal, B-roll plan viewer |
| Windows PE | built by the Windows GitHub Actions workflow and attached to releases |
| CI and Windows | GitHub Actions test workflow and Windows portable artifact workflow |
| SRT transcript import and LLM retake culling | implemented |
| Local Faster-Whisper with whisper.cpp fallback, and ASR HTTP | implemented; pinned small model bundled in release builds |
| Local filesystem browser with allowlisted roots | implemented; no media upload |
| URL import | implemented via optional yt-dlp; external policy and host allowlist apply |
| Webhook publishing | implemented; targets, persistent queue, scheduler, metadata generation |
| Multimodal analysis | implemented; audio-emotion heuristics, motion, optional OpenCV faces, and OpenAI-compatible LLM vision |
| Jobs, job REST routes, SSE, live MCP jobs | implemented for the portable and recipe paths, including per-step checkpoints and step-scoped runs |
| MCP: fifty-two tools and four resources | implemented; recipes, step/batch runs, analysis, capabilities, models, staged edits, jobs, export, resources |
| Rack UI driving real portable and recipe jobs | implemented; Recipes (first tab), Speech/Edit/Shorts/Studio/Export/Models/Services/Providers, logs, overrides, path picker |
| Project-scoped routes, revisions, transcript API, presets | implemented; per-module rerun is typed 501 |
| Shorts selection/rendering and API download | implemented; prompt/reprompt, explainable virality score, auto hook, filler cuts, censor, 9:16, 1:1, 16:9, optional source window |
| Social metadata | implemented; deterministic title, description, and hashtags for YouTube, TikTok, Instagram, LinkedIn |
| Caption branding | implemented; keyword highlight, LLM emoji map, brand vocabulary, profanity mask, 30 language codes, and custom font assets |
| Short thumbnails | implemented; frame extraction plus caption-style title overlay |
| Speech enhancement | implemented for rendered Shorts; high-pass, FFT denoise, loudnorm |
| Watermark overlay | implemented; PNG/JPEG asset store, position, margin, scale, opacity |
| Background music | implemented; looping bed, volume, fades, sidechain ducking |
| Voice-over | implemented; OpenAI-compatible TTS, mixed over a Short |
| Intro/outro | implemented; image cards with configurable durations |
| Dubbing | implemented; translation plus external TTS over a Short |
| Brand templates | implemented; reusable caption, overlay, music, and intro/outro bundles |
| Project templates and config I/O | implemented; flat non-secret options, CRUD, export/import |
| Audio-energy curation | implemented; loud-peak intervals boost Short scores |
| Scene-change curation | implemented; FFmpeg scene cuts boost Short scores |
| Motion tracking | implemented; frame-difference focus estimation for reframing |
| Face tracking | optional; OpenCV face detection with motion fallback |
| Per-Short editor | implemented; trim, retitle, reframe, caption overrides, re-render |
| Capability/provider discovery and external policy | implemented; external providers are opt-in and globally blockable |
| NLE audio fades | implemented in FCPXML, xmeml, and Kdenlive |
| Direct main-timeline MP4 | implemented with H.264/AAC and timeline filter graph |
| Clip transitions | crossfade and fade-to-black in FCPXML, XMEML, and MP4 |
| Speaker turns | heuristic or optional pyannote model, with speaker-colored captions |
| B-roll | local assets or Pexels stock, URL-keyed cache, full-frame Short overlays |
| Split-screen | two-panel Short rendering, auto for dialogue, optional second source and audio mix |
| Local TTS | Piper CLI voice-over through API and Short editor |
| Folder batches | implemented; sequential queue, per-item jobs, cancellation, checkpoints |
| Keyframed progressive zooms | implemented in FCPXML, XMEML, and direct MP4 |
| Clip transitions | implemented in FCPXML, XMEML, and MP4; Kdenlive pending |

Every stub has a strict `xfail` contract in `tests/contract/`.

## Start here

| Document | Read it when |
| --- | --- |
| [PRD](prd.md) | You need the normative requirements and acceptance criteria |
| [Architecture](architecture.md) | You need the boundaries, flow, and package map |
| [Data model](data-model.md) | You are changing state, presets, or schemas |
| [Timebase](timebase.md) | You are touching frames, samples, pads, or exports |
| [Pipeline](pipeline.md) | You are implementing or debugging a run |
| [Recipes](recipes.md) | You are authoring, validating, or running a recipe DAG |
| [Cache](cache.md) | A rerun is slower than it should be |
| [Testing](testing.md) | You are adding tests or running a release gate |
| [API](api.md) | You are wiring the UI or a script |
| [MCP](mcp.md) | You are connecting an agent |
| [UI specification](ui-spec.md) | You are building the rack |
| [Exporters](exporters.md) | You are writing FCPXML, xmeml, or Kdenlive MLT |
| [Security](security.md) | You are handling paths, secrets, or prompts |

## Module specifications

1. [Ingest](modules/01-ingest.md)
2. [Voice activity detection](modules/02-vad.md)
3. [Transcription](modules/03-transcribe.md)
4. [Retake culling](modules/04-retakes.md)
5. [J-cuts and L-cuts](modules/05-jl-cuts.md)
6. [Framing and zooms](modules/06-zooms.md)
7. [Vertical shorts](modules/07-shorts.md)
8. [Export](modules/08-export.md)

Each spec lists purpose, inputs, outputs, config, algorithm, failures, and tests.

## Manuals

| Manual | Audience |
| --- | --- |
| [Portable executable](manuals/portable.md) | Running the onefile build on Linux or Windows |
| [User](manuals/user.md) | Editors |
| [Operator](manuals/operator.md) | Whoever installs and runs the machine |
| [Developer](manuals/developer.md) | Contributors |
| [MCP agent](manuals/mcp-agent.md) | Agents and their operators |
| [NLE import](manuals/nle-import.md) | Editors doing the Resolve/Premiere/Kdenlive handoff |
| [Testing](manuals/testing.md) | QA and release |

## Decisions

| ADR | Title |
| --- | --- |
| [0001](adr/0001-rational-timebase.md) | Rational time is authoritative |
| [0002](adr/0002-hexagonal-modules.md) | Hexagonal boundaries and a fixed rack |
| [0003](adr/0003-secrets-out-of-state.md) | Secrets never enter project state |
| [0004](adr/0004-nle-dialects.md) | One timeline, three NLE dialects |
| [0005](adr/0005-mcp-transports.md) | stdio primary, Streamable HTTP mounted |
| [0006](adr/0006-xml-builder-not-jinja.md) | Typed XML builder, Jinja2 only for prompts and ASS |
| [0007](adr/0007-retake-guard.md) | A guard enforces keep-last |
| [0008](adr/0008-cpu-first.md) | CPU-first defaults |
| [0009](adr/0009-single-user-local.md) | Local single-user runtime |
| [0010](adr/0010-portable-single-executable.md) | One portable executable per OS |
| [0011](adr/0011-local-filesystem-browser.md) | Allowlisted local filesystem browser |

## Document rules

- English only. Identifiers, comments, logs, and UI strings included.
- One source of truth. The PRD owns requirements; the ADRs own decisions; the
  module specs own algorithms; the tests own behavior.
- If code and doc disagree, the test decides and the doc is fixed in the same
  change.
- No secrets, private media, or personal paths in examples.
