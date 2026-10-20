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
      │ FFmpeg · Silero ONNX · whisper.cpp/ASR   │
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
| `domain/timebase.py` | Rational frame and sample arithmetic, frame coverage, pads |
| `domain/config.py` | Pydantic module configs and CPU-first defaults |
| `domain/state.py` | `ProjectState` and its JSON Schema |
| `domain/planning.py` | Cache-status planning and upstream rules |
| `domain/retakes.py` | Repetition clusters and the keeper guard |
| `domain/timeline.py` | Overlap and packing checks |
| `domain/paths.py` | Path allowlist jail |
| `domain/redact.py` | Secret redaction |
| `application/cache.py` | Canonical module hashing |
| `application/timeline_builder.py` | Deterministic cuts, J/L boundaries, fades, zoom metadata |
| `application/export_service.py` | One validated timeline to three NLE artifacts |
| `application/portable.py` | Ingest → VAD → timeline → export run |
| `runtime.py` | Portable home, bundled binary discovery, UI discovery |
| `cli.py` | Unified `videoflow` command surface |
| `application/runner.py` | Executes a `RunPlan` (stub) |
| `application/jobs.py` | In-process jobs with progress, cancel, and bounded concurrency |
| `application/telemetry.py` | Per-stage timestamps, progress, and bounded logs |
| `modules/` | The eight rack modules (fingerprints live, engines stubbed) |
| `adapters/ffmpeg.py` | FFprobe ingest, PCM extraction, digest, silencedetect VAD |
| `adapters/silero.py` | Silero v5.1.2 ONNX inference and speech-window merging |
| `adapters/whisper.py` | Local whisper.cpp CLI adapter |
| `adapters/asr.py` | OpenAI-compatible `/audio/transcriptions` client |
| `adapters/llm.py` | OpenAI-compatible retake client |
| `exporters/` | FCPXML, xmeml, OTIO implemented; MP4 stub |
| `api/` | FastAPI app, job routes, SSE, UI mount, CLI |
| `mcp_server/` | Tool registry, SDK server, stdio CLI |

## 3. The eight modules

Execution order is fixed. The graph is a line with two side inputs, not a free
DAG. This keeps cache reasoning and UI ordering simple.

```
ingest ──► vad ──────────────┐
   │                          ├──► jl_cuts ──► zooms ──┐
   └──► transcribe ──► retakes┘                        ├──► export
                └──────────────► shorts ───────────────┘
```

| Module | Reads | Writes | Engine |
| --- | --- | --- | --- |
| ingest | source path | media info, PCM, proxy | FFmpeg |
| vad | PCM | speech sample spans | Silero ONNX (FFmpeg fallback) |
| transcribe | PCM | sentences and words | whisper.cpp / ASR HTTP; Faster-Whisper next |
| retakes | transcript | culls, guard restores | LLM + domain guard |
| jl_cuts | VAD spans, culls | video and audio segments | domain + timebase |
| zooms | segments | transforms | domain rules |
| shorts | transcript, culls | vertical source windows | LLM + FFmpeg |
| export | all of the above | FCPXML, xmeml, OTIO, MP4 | lxml, OTIO, FFmpeg |

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
