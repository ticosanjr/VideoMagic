# VideoFlow documentation

Everything here is English. The original Portuguese brief is archived and
non-normative at [origin/prd-pt.md](origin/prd-pt.md).

## Implementation status (2.25.1)

| Area | State |
| --- | --- |
| Rational time, state, cache, planning, retake guard, path jail | implemented |
| FFmpeg ingest and PCM fingerprint | implemented |
| Silero VAD via ONNX Runtime with FFmpeg `silencedetect` fallback | implemented |
| Deterministic timeline, J/L-cuts, fades, punch-ins | implemented |
| FCPXML 1.9/1.10, xmeml v4, native Kdenlive MLT export | implemented |
| Portable artifacts | 2.25.1 lean Linux binary and AppImage; speech weights are optional downloads from the Models tab |
| Run history | persisted in `work/run-history.json`, including failed runs, paginated by `GET /api/v1/runs` |
| Diagnostics | doctor covers FFmpeg capabilities, CUDA/ONNX, SQLite, providers, services, models, disk, and settings; support bundle ZIP |
| NLE validation | `scripts/validate_nle.py` and `POST /api/v1/exports/validate` |
| Schema gates | recipe and project-state `schema_version` migration |
| Maintenance | output and global-cache pruning by age/size |
| Preview proxy | on-demand 540p MP4 for browser preview |
| Step logs | per-node log viewer backed by `GET /api/v1/jobs/{id}/logs?module=...` |
| Content cycle | idea/research/script/storyboard/assets, real audio master/titles/analytics/review, color/LUT, thumbnail variants, and publish bypass |
| Assets | local library scan, search, tags, license, delete, and file serving |
| Timeline | canvas editing with multi-select, batch edits, markers, track mute/solo/lock enforcement, clip thumbnails, drag/trim/split/ripple/group trim/slip, undo/redo, snapping, real per-clip waveforms, virtualization, preview scheduler, render queues, per-clip transition/fade/scale, and B-roll approval |
| Operational store | SQLite WAL with `schema_version=2`, migration from JSON, backup/restore, and idempotent job requeue |
| Release | tag-triggered Linux/AppImage/Windows/SBOM release workflow |
| Batch persistence | SQLite is read first, JSON stays as an interchange mirror; paginated API/UI |
| Job persistence | SQLite is read first and JSON fills gaps; interrupted jobs are requeued on startup |
| Professional shell | five areas (Produce/Edit/Runs/Library/Setup), command palette, shortcuts, activity, notifications, runs dashboard, pause/resume, priority ([shell.md](shell.md)) |
| Timeline editing | group trim, slip, slide, ripple trim, duplicate, comments, context menu, real waveforms, virtualization, preview scheduler, incremental Shorts, and tracked lock/mute/solo ([timeline.md](timeline.md)) |
| Content quality | golden set and channel profiles, TF-IDF/optional embedding B-roll with licenses, SFX library, delivery package, hook/duration A/B, dubbing alignment and review, and a localized recipe ([quality.md](quality.md)) |
| NLE finishing | native titles, markers, colour filters, B-roll lane, and audio master in FCPXML/XMEML/Kdenlive, with `scripts/qa_nle.py` ([nle-qa.md](nle-qa.md)) |
| Plugins | exporter and provider registration, manifest permissions, static sandbox allowlist ([plugins.md](plugins.md)) |
| UI guidance | naming, tooltips, microcopy, empty states, units ([ui-copy.md](ui-copy.md)) |
| Error catalog | codes, HTTP status, meaning, next action ([errors.md](errors.md)) |
| Release gates | 2.14 evidence and the four open 3.0 blockers ([3.0-blockers.md](3.0-blockers.md)) |
| Coverage | per-layer baseline and the remaining gap ([coverage.md](coverage.md)) |
| Voice cloning | Explicit deferral, consent, and acceptance criteria ([voice-clone.md](voice-clone.md)) |
| Settings | searchable settings with units, help tips, discard/reset ([settings.md](settings.md)) |
| Copilot | LLM recipe drafts and timeline edit plans, provider/service setup, validation rules ([copilot.md](copilot.md)) |
| Projects and assistant | Project records, allowlisted tool-calling with approval/diff/cost, run graph, variant comparison ([projects-assistant.md](manuals/projects-assistant.md)) |
| Recut and recipe library | Recut Replacement (+ retakes), detailed VAD/cut controls, favorites/recent/tags on the server ([recipes.md](recipes.md)) |
| Typed ports | Step inputs/outputs, inspector/edge wiring, branch isolation, input-hash cache ([recipes.md](recipes.md)) |
| Node IO | Media pickers and output-folder policy inside nodes, Inputs/Config/Outputs layout |
| Recut presets | Podcast, Lecture, and Social variants with tuned VAD/cut settings |
| Voice clone shell | Contracts, consent metadata, status/profiles API, no synthesis |
| Integrations | OpenCode and Paperclip over MCP/REST with DeepSeek, prompts, config, and troubleshooting ([integrations.md](integrations.md)) |
| Hardening | fault injection, log rotation, scheduled backups, AA keyboard/focus/reduced-motion, 1,000-clip writer stress ([hardening.md](hardening.md)) |
| Cancellation | FFmpeg runs in its own process group; render and preview cancel within one poll and delete partial output |
| Queue claim | SQLite `BEGIN IMMEDIATE` claim with lease ownership, heartbeat, and expired-lease recovery |
| Frame cache | Per-revision, per-height JPEG frames under `preview/frames/<revision>/` |
| Incremental render | Segment cache with per-clip fades and overlays; crossfades fall back to the full graph |
| Batch resume | resume failed/cancelled batches and skip completed items |
| Preview | synced MP4 preview plus waveform; background 540p proxy with titles, color, and audio-master filters |
| MLT smoke | optional `melt` render check for generated Kdenlive projects |
| Recipe UI | inline node fields, array JSON, undo/redo, cycle prevention, saved layout, per-step progress, NLE validation |
| Windows PE | not part of the local Linux release; cross-build separately if needed |
| CI and Windows | GitHub Actions test workflow and Windows portable artifact workflow |
| SRT transcript import and LLM retake culling | implemented |
| Local Faster-Whisper with whisper.cpp fallback, and ASR HTTP | implemented; pinned small model bundled in release builds |
| Local filesystem browser with allowlisted roots | implemented; no media upload |
| URL import | implemented via optional yt-dlp; external policy and host allowlist apply |
| Webhook publishing | implemented; targets, persistent queue, scheduler, metadata generation |
| Translation and audio QA | implemented; LLM transcript translation plus EBU R128 loudness/true-peak QA |
| Secrets and failover | implemented; env/keyring/0600 secret store and ordered LLM provider failover |
| Recipe automation | implemented; SQLite schedules, retry/backoff, run history, watch-file signatures, and a local scheduler |
| Review and thumbnails | implemented; approve/reject with comment threads and A/B thumbnail CTR metrics |
| Settings | implemented; settings.json with runtime, paths, models, automation, quality, LLM/speech/TTS, stock, translation, and export/import |
| Library | implemented; brand/project templates, presets, fonts, images, and music |
| Managed services | implemented; SQLite service definitions with start/stop, health, autostart, and logs |
| Multimodal analysis | implemented; audio-emotion heuristics, motion, optional OpenCV faces, and OpenAI-compatible LLM vision |
| Jobs, job REST routes, SSE, live MCP jobs | implemented for the portable and recipe paths, including per-step checkpoints and step-scoped runs |
| MCP: 78 tools and 5 resources | implemented; recipes, step/batch runs, analysis, capabilities, models, jobs, timeline, overlays, comments, Copilot, cost, plugins, backup, exports, resources |
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
| Speaker turns | heuristic or optional pyannote model; installed local model auto-detected |
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
| [UI specification](ui-spec.md) | Recipe studio and canvas timeline |
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
