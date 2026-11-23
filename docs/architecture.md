# Architecture

## 1. Shape

VideoFlow is a hexagon. The domain owns time, state, planning, and retake rules.
Adapters own FFmpeg, ONNX, CTranslate2, HTTP, and MCP. The UI and agents are peers.

```
┌──────────────────────┐          ┌──────────────────────┐
│  SvelteKit rack      │          │  MCP host            │
│  HTTP + SSE          │          │  stdio / HTTP        │
└──────────┬───────────┘          └──────────┬───────────┘
           │                                 │
      ┌────▼─────────────────────────────────▼────┐
      │  FastAPI (loopback)     MCP server        │
      │  routes + SSE           tools + resources │
      └────────────────────┬──────────────────────┘
                           │ identical application services
      ┌────────────────────▼──────────────────────┐
      │  PipelineRunner · Cache · Jobs · Export   │
      │  TimelineProjectState (single document)   │
      └────────────────────┬──────────────────────┘
                           │ ports
      ┌────────────────────▼──────────────────────┐
      │ FFmpeg · Silero · Faster-Whisper/cpp/ASR │
      │ OpenAI-compatible LLM · filesystem       │
      └───────────────────────────────────────────┘
```

Rules:

1. `domain/` imports no adapter, web, or media library.
2. HTTP and MCP call the same service functions. Neither contains edit logic.
3. The UI renders state. It does not compute cuts.
4. One timeline model feeds every exporter. Exporters never re-run analysis.

## 2. Package map

| Path | Responsibility |
| --- | --- |
| `domain/` | Pure contracts: rational timebase, state, planning, timeline, retakes, paths, redaction, errors |
| `core/recipe.py` | Versioned recipe DAG contract and validation |
| `core/context.py` | Typed artifact/state context shared by steps |
| `core/media_contract/` | PCM, loudness, frame, and codec invariants |
| `core/execution.py` | Execution records and telemetry types |
| `core/nvenc.py` | NVENC capability and argument contracts |
| `steps/` | Atomic pipeline steps, params models, ports, registry, cache, and self-heal |
| `steps/decupage.py` | Canonical decupage calibration; `decoupage.py` is a compatibility shim |
| `steps/shorts_captions.py` | Canonical Short caption pipelines (`shorts.captions` and `short.captions`) |
| `steps/shorts_render.py` | Canonical Short render pipelines (`shorts.render` and `short.render`) |
| `engine/runner.py` | Topological/linear execution, progress, telemetry, and report writing |
| `engine/recipes/` | Built-in and operator recipe definitions and catalog |
| `engine/checkpoint.py` | Step checkpoints and resumable execution |
| `application/` | Application services grouped by area (jobs, database, pipeline, QA, delivery, styles, intelligence) |
| `application/intelligence/` | LLM providers, routing, budget, circuit breaker, and JSON contracts |
| `application/decupage/` | Decupage review and snap services |
| `application/short_composition/` | Short plan, caption geometry, rhythm, and render command builders |
| `domains/asr/` | Faster-Whisper and whisper.cpp CLI adapters, HTTP/remote ASR, profiles |
| `domains/audio/` | Finalize, mixing, analysis, synthesis, and audio DSP |
| `domains/vision/` | Matte, scene vision, tracking, and vision helpers |
| `domains/media/` | Media probing, B-roll, and media-side services |
| `domains/toolkit/` | Shared domain utilities |
| `adapters/ffmpeg/` | FFmpeg/FFprobe package: probe, PCM, render, overlays, audio filters |
| `adapters/llm.py` | Delegates to the canonical OpenAI-compatible provider |
| `adapters/opencode.py` | Constrained OpenCode CLI bridge |
| `adapters/vision.py` | Vision JSON adapter over the shared provider parser |
| `adapters/tts.py`, `diarization.py`, `silero.py`, `yamnet.py`, `resolve.py` | External engines and Resolve integration |
| `exporters/` | FCPXML, xmeml, and native Kdenlive MLT writers; no MP4 stub |
| `api/` | FastAPI app, REST routes, SSE streams, error mapping, UI mount |
| `mcp_server/` | Guard, strict 17/22 tool profiles, resources, prompts, stdio CLI |
| `bootstrap/` | OpenCode workspace generation, styles/workflows, GPU kit bootstrap |
| `packages/vf-shared/` | Shared compute router, GPU client, scene rules, contracts, discovery |
| `packages/gpu-worker/` | Windows GPU worker app, handler registry, NVENC/matte/ASR/scene handlers |
| `templates/` | OpenCode skills/commands, AGENTS template, styles/workflows, Windows wheels |
| `styles/` | Canonical 22 Markdown styles (single source; workspace `presets/` is a copy) |
| `workflows/` | Canonical workflow Markdown files |
| `ui/` | SvelteKit rack; renders state and never computes cuts |
| `cli.py`, `runtime.py`, `plugin_api.py` | Unified CLI, portable home/binary discovery, plugin surface |

## 3. Pipeline families

Steps are registered atomically and composed by recipes or `vf_run`. The common
families are:

| Family | Reads | Writes | Engine |
| --- | --- | --- | --- |
| ingest/session | source paths | media info, PCM, normalized sources | FFmpeg |
| speech | PCM | VAD spans, sentences, words, ASR cleanup | Silero, Faster-Whisper, whisper.cpp, HTTP ASR |
| editorial | transcript | culls, retakes, clean transcript, decupage plan | LLM + domain rules |
| timeline | transcript, VAD, culls | canonical segments, overlays, beat maps | domain + timebase |
| shorts | selected ranges | composition plan, captions, rendered Shorts | FFmpeg + NVENC |
| audio | stems, TTS, music, SFX | final loudness-normalized mix | FFmpeg + audio domains |
| qa/export | timeline + artifacts | QA reports, MP4, FCPXML, xmeml, Kdenlive MLT | FFmpeg, lxml, XML writers |

The exact step list, params, and ports are served on demand through
`vf://docs/steps` and `vf://docs/steps/{step_type}`.

A bypassed module emits an identity result: the same input payload, an explicit
`bypassed: true` marker, and a hash that includes the disabled flag. Downstream
hashes change, which is correct: the pipeline is now different.

## 4. State and persistence

```
<project>/
  .videoflow/
    project_state.json
    lock
    revisions/000001.json ...
    cache/ingest/<hash>/...
    work/source.wav
    work/proxy.mp4
    exports/...
```

- The JSON document is the contract; the Pydantic model mirrors it.
- Operational records (jobs, assets, batches, schedules, services) live in
  `videoflow.db` under the VideoFlow home. SQLite is read first; JSON files are
  an interchange mirror and a migration source.
- Writes are atomic: write a sibling temp file, fsync, replace.
- Revisions are append-only snapshots. There is no silent undo.
- The lock is an OS advisory lock. It serialises jobs, not readers.
- Cache directories are content-addressed; a failed run never deletes the last
  good entry.

## 5. Execution model

1. A request resolves a project through the path jail.
2. The runner builds a status map from the persisted hashes.
3. `plan_run` decides the module list.
4. A job acquires the project lock and moves through the plan.
5. After each module, the runner writes artifacts, then state, then the next
   revision.
6. SSE emits `module_started`, `module_progress`, `module_done`, `module_failed`,
   and `job_done`.
7. Cancellation is checked between modules and by the FFmpeg/Whisper subprocess
   supervisor.

Long transcription runs in a subprocess so it can be cancelled and so a native
crash cannot take the API down. VAD and export may run in worker threads because
they are short or I/O-bound.

## 6. Timing model

Authoritative:

- video: integer frame index at `fps_num / fps_den`
- audio: integer sample index at `audio_sample_rate`
- fades and offsets: integer samples

Derived:

- seconds for the UI and prompts
- rational FCPXML strings such as `1001/30000s`

A video edge expands to cover its audio pad, never the reverse. See
[timebase.md](timebase.md).

## 7. Error model

| Class | Code | HTTP | MCP |
| --- | --- | --- | --- |
| `VideoFlowError` | `videoflow_error` | 400 | structured error |
| `UpstreamDirtyError` | `upstream_dirty` | 409 | `isError` with ancestors |
| `ModuleBypassedError` | `module_bypassed` | 409 | structured error |
| `JobAlreadyRunningError` | `job_already_running` | 409 | structured error |
| `PathJailError` | `path_not_allowed` | 403 | structured error |
| `InvalidRetakeIdsError` | `invalid_retake_ids` | 422 | structured error |
| `InvalidTimeError` | `invalid_time` | 422 | structured error |
| `NotImplementedCapabilityError` | `not_implemented` | 501 | structured error |

The scaffold already implements these payloads. MCP returns them as structured
content rather than protocol-level faults, so an agent can read the code.

## 8. Security boundary

VideoFlow is single-user. The boundary is the process account plus the configured
allowed roots. It is not a multi-tenant authorisation system.

- Bind to loopback. Do not expose the port.
- Resolve every incoming path through `resolve_allowed`.
- Follow symlinks before the allowlist check, so a link cannot escape.
- Keep secrets outside the project state and redact logs.
- Treat transcripts, presets, and file names as untrusted data in prompts.

See [security.md](security.md).

## 9. Deployment

One machine, one Python environment, one Node build. The API serves the built UI
or the UI dev server proxies to it. The MCP stdio command is registered per host
(for example OpenCode or Claude Desktop). The HTTP MCP endpoint is the same
FastAPI process at `/mcp`.

No database, queue, or container is required for v1. A future multi-user version
would replace the file lock and in-process jobs, not the domain.

## 10. Decisions

| ADR | Decision |
| --- | --- |
| [0001](adr/0001-rational-timebase.md) | Rational time is authoritative |
| [0002](adr/0002-hexagonal-modules.md) | Hexagonal boundaries and fixed rack |
| [0003](adr/0003-secrets-out-of-state.md) | Secrets never enter state |
| [0004](adr/0004-nle-dialects.md) | One timeline, three NLE dialects |
| [0005](adr/0005-mcp-transports.md) | stdio primary, Streamable HTTP mounted |
| [0006](adr/0006-xml-builder-not-jinja.md) | Typed XML builder, Jinja2 only for prompts/ASS |
| [0007](adr/0007-retake-guard.md) | A guard enforces keep-last |
| [0008](adr/0008-cpu-first.md) | CPU-first defaults |
| [0009](adr/0009-single-user-local.md) | Local single-user runtime |
