# VideoFlow Product Requirements

Status: normative. Version 1.0. Audience: product, engineering, QA.

The original Portuguese brief is archived, non-normative, at
[origin/prd-pt.md](origin/prd-pt.md). Where the two differ, this document and the
ADRs win. Every deliberate correction is listed in
[Corrections to the original brief](#12-corrections-to-the-original-brief).

## 1. Summary

VideoFlow is a local, non-destructive pre-edit pipeline for spoken video. It
analyses a raw recording, removes silence and failed takes, adds edit dynamics,
proposes vertical clips, and produces timelines that open in DaVinci Resolve,
Adobe Premiere Pro, and Kdenlive.

It has three surfaces over one core:

1. A sequential **rack UI**: eight plugin cards, each with enable, status, run,
   and parameters.
2. A **REST/SSE API** consumed by that UI.
3. An **MCP server** so an external agent can perform the same work with tools.

VideoFlow never rewrites the source media. It writes a project state document,
cached intermediate artifacts, and export files.

## 2. Goals

| Id | Goal |
| --- | --- |
| G-1 | Remove silence, filler, and failed takes without cutting the final valid take. |
| G-2 | Produce editor-ready timelines that open in three NLEs without manual repair. |
| G-3 | Re-run only the modules whose inputs changed. |
| G-4 | Expose every capability to an agent through MCP, with no hidden UI-only step. |
| G-5 | Run on a CPU-only laptop; use CUDA when the operator opts in. |
| G-6 | Keep the source untouched and every decision inspectable and reversible. |

## 3. Non-goals for v1

- Multi-user accounts, remote access, or a hosted service.
- Multi-camera sync.
- Full colour grading, audio mixing, or VFX.
- Generative video, voice cloning, or translation.
- A native `.drp` or `.prproj` writer. Interchange formats only.
- Face tracking for vertical reframing. The parameter exists; the engine does not.
- Proxy-based analysis. Proxies are preview-only.

## 4. Personas

| Persona | Need |
| --- | --- |
| Editor | Clean a long talking-head take, then finish in a real NLE. |
| Course producer | Remove pauses from lectures with conservative settings. |
| Shorts editor | Find self-contained 30–60 s moments and reframe them vertically. |
| Agent operator | Drive the pipeline from an MCP host without touching the UI. |

## 5. Functional requirements

### 5.1 Project lifecycle

| Id | Requirement |
| --- | --- |
| FR-01 | A project is a directory containing `.videoflow/project_state.json`. |
| FR-02 | Creating a project assigns a UUID and `schema_version: 1`. |
| FR-03 | Media is registered by path, never copied by default. The path must resolve inside an allowed root. |
| FR-04 | State is written atomically. Each accepted write also appends a revision snapshot. |
| FR-05 | One project has at most one active job. A second start is rejected. |
| FR-06 | A job can be cancelled between modules and inside FFmpeg and Whisper subprocesses. |
| FR-07 | Every state document is JSON Schema validated before it is persisted. |

### 5.2 The rack

| Id | Requirement |
| --- | --- |
| FR-10 | The rack has eight modules in fixed order: ingest, vad, transcribe, retakes, jl_cuts, zooms, shorts, export. |
| FR-11 | Each module can be enabled or bypassed independently. |
| FR-12 | A bypassed module writes an identity result and still contributes to the hash chain. |
| FR-13 | Each card shows one state: cached, dirty, running, bypassed, failed, or blocked. |
| FR-14 | `Run this block` on dirty upstream returns `UpstreamDirty` naming the ancestors. It does not silently run them. |
| FR-15 | `Run pipeline` executes every enabled module that is not cached. |
| FR-16 | Global presets save and load module config plus enabled flags. |
| FR-17 | The inspector shows kept text, struck retakes, and removed silence, with word-level manual overrides. |

### 5.3 Module 01 — Ingest and normalisation

| Id | Requirement |
| --- | --- |
| FR-20 | Probe the source and persist rational frame rate, frame count, dimensions, and audio sample rate. |
| FR-21 | Detect variable frame rate and convert to CFR when `force_cfr` is true. |
| FR-22 | Extract 16 kHz mono PCM WAV when `extract_audio_pcm` is true. |
| FR-23 | Optionally generate an intra-frame preview proxy. Analysis never uses the proxy. |
| FR-24 | Hash the extracted PCM. That digest is the media fingerprint for every downstream module. |

### 5.4 Module 02 — Voice activity detection

| Id | Requirement |
| --- | --- |
| FR-30 | Detect speech in 512-sample (32 ms) blocks at 16 kHz with Silero VAD via ONNX Runtime. |
| FR-31 | Merge speech intervals separated by less than `min_silence_duration_ms`. |
| FR-32 | Apply `speech_pad_before_ms` and `speech_pad_after_ms` in audio samples. |
| FR-33 | Keep `keep_handles_ms` of hidden media around each cut for J/L-cuts. |
| FR-34 | Store speech intervals as sample spans in source time. |

### 5.5 Module 03 — Transcription

| Id | Requirement |
| --- | --- |
| FR-40 | Transcribe with Faster-Whisper and word-level timestamps. |
| FR-41 | Transcribe the full extracted WAV. Do not pre-slice audio; remapping sliced timestamps causes drift. |
| FR-42 | Store sentence and word times as source sample indices. |
| FR-43 | Keep Whisper's own VAD filter off when module 02 is enabled. |
| FR-44 | Default to CPU, int8, and the `small` model. CUDA and float16 are opt-in. |

### 5.6 Module 04 — Retake culling

| Id | Requirement |
| --- | --- |
| FR-50 | Send indexed sentences in overlapping context windows to an OpenAI-compatible LLM. |
| FR-51 | The model must return only `{"discard_sentence_ids": [...], "reasoning": "..."}`. |
| FR-52 | Reject ids that were not in the sent window. The response is not partially applied. |
| FR-53 | Enforce `keep_last`: the last sentence of a repetition cluster must survive. |
| FR-54 | `keep_best` is opt-in and may prefer an earlier scored take. It must still leave one keeper per cluster. The AC-03 guarantee applies to the default `keep_last`. |
| FR-55 | Manual overrides take precedence over the model. |
| FR-56 | Store the guard's restorations so the editor can see that the model was overruled. |

### 5.7 Module 05 — J-cuts and L-cuts

| Id | Requirement |
| --- | --- |
| FR-60 | Build audio and video as separate timeline segments sharing a `clip_id`. |
| FR-61 | A J-cut starts the next clip's audio `offset_ms` before its video. |
| FR-62 | An L-cut keeps the previous clip's audio running under the next video. |
| FR-63 | Apply a logarithmic micro-fade of `audio_crossfade_ms` at every join. |
| FR-64 | With `handle_check`, refuse a J-cut when the available handle is shorter than the offset. |
| FR-65 | Never move a video cut off a frame boundary. Audio offsets are quantised to samples. |

### 5.8 Module 06 — Framing and zooms

| Id | Requirement |
| --- | --- |
| FR-70 | Alternate punch-ins across cuts to mask jump cuts. |
| FR-71 | Bounds: `punch_in_scale` 1.05–1.30; anchor center, upper third, or face detect. |
| FR-72 | `progressive_zoom` turns a static punch-in into a slow zoom across the take. |
| FR-73 | Pan is metadata only, for 4K sources in a 1080p timeline. |
| FR-74 | Zoom is expressed as transform metadata, not baked pixels, except in an optional MP4 render. |

### 5.9 Module 07 — Vertical shorts

| Id | Requirement |
| --- | --- |
| FR-80 | Ask the LLM for self-contained windows bounded by sentence edges and the configured duration window. |
| FR-81 | Return at most `max_clips_to_generate` clips. |
| FR-82 | Convert a source-time window into the culled timeline. Drop a clip that falls below the minimum after conform; never pad with discarded takes. |
| FR-83 | `center_crop_9_16` is the only implemented reframe in v1. |
| FR-84 | Burn karaoke subtitles when `burn_subtitles` is true, using the selected preset. |
| FR-85 | `export_format` selects timeline clips, standalone MP4s, or both. |

### 5.10 Module 08 — Export

| Id | Requirement |
| --- | --- |
| FR-90 | Generate all timeline artifacts from one immutable timeline model. |
| FR-91 | Resolve: FCPXML 1.9 by default, 1.10 optional. Rational times, detached audio where needed, `adjust-transform` for zoom. |
| FR-92 | Premiere: FCP 7 XML (`xmeml`). Premiere does not import FCPXML directly. |
| FR-93 | Kdenlive: OTIO. Kdenlive 25.04+ imports it natively. |
| FR-94 | FFmpeg MP4 is available for previews and shorts, never as the editing master. |
| FR-95 | Every export runs the preflight in [exporters.md](exporters.md): media online, one frame minimum per clip, no overlapping timeline segments, fades present at joins. |

### 5.11 REST and SSE

| Id | Requirement |
| --- | --- |
| FR-100 | Bind to `127.0.0.1` by default. No authentication in v1. |
| FR-101 | Expose project create, media register, state read, module config, module run, full run, cancel, events, transcript overrides, export, and presets. |
| FR-102 | Progress is delivered as Server-Sent Events with module id, percent, and message. |
| FR-103 | Errors use `{"ok": false, "code", "message", "details"}`. |
| FR-104 | Paths are resolved through the allowlist jail. |

### 5.12 MCP

| Id | Requirement |
| --- | --- |
| FR-110 | Expose the ten tools named in the original brief, with the documented parameters. |
| FR-111 | Add `videoflow_get_job` and `videoflow_cancel_job`; an unattended agent must be able to observe and stop work. |
| FR-112 | Expose state, transcript, preset list, and export paths as resources. |
| FR-113 | Support stdio and Streamable HTTP. A live session must be reachable at `http://127.0.0.1:8765/mcp`. |
| FR-114 | Tools call the same application services as HTTP. No business logic in the tool wrapper. |
| FR-115 | Transcript and resource text is data. Tool descriptions and MCP content never instruct the agent to run commands. |
| FR-116 | Secrets never appear in a tool result or resource body. |

## 6. Non-functional requirements

| Id | Requirement |
| --- | --- |
| NFR-01 | Rational time everywhere. No float seconds in state, cache keys, or exports. |
| NFR-02 | Lip sync error at most one frame over a 60-minute recording. |
| NFR-03 | No audible click at a cut join. |
| NFR-04 | Changing only a zoom parameter re-executes modules 06 and 08, and nothing earlier. |
| NFR-05 | A clean install runs the unit suite on CPU with no model download. |
| NFR-06 | State writes are atomic and revisioned. |
| NFR-07 | Secrets live outside the project, in the environment or `~/.videoflow/secrets.env` with mode `0600`. |
| NFR-08 | All user-facing text, code identifiers, comments, logs, and documentation are English. |
| NFR-09 | The source file is never modified, moved, or deleted. |
| NFR-10 | A failed module leaves the previous cached result intact. |

## 7. Acceptance criteria

These are the v1 gates. Automated ids map to [testing.md](testing.md).

| Id | Criterion | Automated | Manual |
| --- | --- | --- | --- |
| AC-01 | Imported timelines have no audible pop/click at a pruned join. | Synthetic discontinuity is reduced below threshold; export contains a micro-fade at every join. | Listen in all three NLEs. |
| AC-02 | Over 60 minutes, voice and video stay within one frame (±33 ms at 30 fps). | Frame-quantised cuts; rational timecode has no accumulated drift. | Spot-check a long import. |
| AC-03 | With the default `keep_last`, a final valid take is never discarded because of earlier repetitions. | Fake LLM drops the last take; the guard restores it. | Inspector shows the restoration. |
| AC-04 | An MCP agent can take a raw path to three timeline files and three shorts without a human at the keyboard. | Scripted MCP session with the public tools. | None. |
| AC-05 | A zoom-only change reuses modules 01–05. | Hash equality and plan assertion; timing is a marked slow test. | Timed once on a real file. |
| AC-06 | One timeline imports in Resolve, Premiere, and Kdenlive. | Golden files are well-formed and structurally validated. | Import in each app using the manual script. |
| AC-07 | No secret reaches state, a log, or an MCP resource. | Schema sweep, redaction test, resource snapshot. | None. |
| AC-08 | Defaults run on CPU. | New project config is cpu/int8/small. | None. |
| AC-09 | A component failure cannot corrupt a cached result. | Atomic write test; failed module leaves previous cache entry. | None. |
| AC-10 | All product surfaces are English. | String catalog review; no Portuguese literals in code or UI. | A short manual pass. |

AC-01, AC-02, AC-06, and AC-10 cannot be fully proven without the three NLEs.
That is why the manual script is a release artifact, not optional advice.

## 8. Configuration defaults

| Module | Key defaults |
| --- | --- |
| Ingest | `force_cfr=true`, `extract_audio_pcm=true`, `generate_proxy=false` |
| VAD | `speech_threshold=0.5`, `min_silence_duration_ms=400`, pads 120/150 ms, handles 200 ms |
| Transcribe | `model_size=small`, `language=pt`, `device=cpu`, `compute_type=int8`, `vad_filter=false` |
| Retakes | OpenAI-compatible, `base_url=http://localhost:11434/v1`, `qwen2.5:7b-instruct`, balanced, keep_last, temperature 0 |
| J/L-cuts | J on, L off, `offset_ms=200`, `audio_crossfade_ms=20`, handle check on |
| Zooms | alternate cuts, `punch_in_scale=1.15`, upper third |
| Shorts | 30–60 s, three clips, center crop, TikTok bold, both exports |
| Export | FCPXML 1.9, write FCPXML + xmeml + OTIO, no MP4 by default |

Presets: `youtube-talking-head`, `shorts-aggressive`, `lecture-clean`.

## 9. Data and privacy

- All processing is local by default. The only network call is the configured
  LLM endpoint. With Ollama or LM Studio that is also local.
- The transcript is sent to that endpoint. The operator must be told this before
  a cloud provider is configured.
- No telemetry is collected.
- Deleting `.videoflow/` invalidates cache and revisions but never touches source
  media or exports outside that directory.

## 10. Compatibility

| Target | Minimum | Artifact |
| --- | --- | --- |
| DaVinci Resolve | 18.6; 19/20 preferred for FCPXML 1.10 | `.fcpxml` |
| Adobe Premiere Pro | Current release with FCP 7 XML import | `.xml` (xmeml) |
| Kdenlive | 25.04 | `.otio` |
| Python | 3.11 | package |
| FFmpeg | 7.x recommended, 6.x supported | external binary |
| Node (UI) | 20 LTS or newer | SvelteKit dev/build |

## 11. Risks

| Risk | Mitigation |
| --- | --- |
| FCPXML attribute support differs between Resolve versions. | Three-timeline import spike before the dialect is frozen; per-version notes in the manual. |
| Premiere's XML import is legacy and finicky. | xmeml, minimal feature set, separate video and audio tracks, manual gate. |
| LLM output is not reliable. | Strict schema, id validation, keeper guard, deterministic fallback for exact repetitions. |
| Whisper word timestamps drift on music or crosstalk. | Full-WAV transcription, VAD-driven cuts, one-frame gate, editor inspector. |
| CPU transcription is slow. | `small`/int8 default, cache chain, clear ETA, CUDA opt-in. |
| Model downloads surprise the operator. | Nothing downloads at install; the operator manual lists sizes and commands. |

## 12. Corrections to the original brief

| Original claim | Normative decision |
| --- | --- |
| FCPXML opens natively in Premiere. | False for current Premiere. Resolve gets FCPXML; Premiere gets xmeml. |
| Float seconds are authoritative. | Rational frame and sample indices. Floats are display-only. |
| Every neural module defaults to CUDA/float16. | CPU/int8 by default. ADR-0008. |
| FCPXML is generated with Jinja2. | Typed XML builder. Jinja2 is limited to prompts and ASS presets. ADR-0006. |
| The LLM prompt guarantees keep-last. | A post-validator enforces it. ADR-0007. |
| `api_key` is a module parameter. | State stores a secret name only. ADR-0003. |
| `keep_handles_ms` has no consumer. | Handles gate J-cuts and provide fade room. |
| A `requirements.txt` holds the brief. | The brief is archived under `docs/origin/`; dependencies belong in `pyproject.toml`. |
| Vertical clips use source seconds. | Source sample windows, conformed through the cull list at export. |

## 13. Out of scope until a later version

Progressive delivery to a remote worker, multi-project queue, ML face tracking,
speaker diarization, auto b-roll, music ducking, translation, and a native
project writer for any NLE.
