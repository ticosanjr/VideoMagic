# Changelog

All notable changes are recorded here. Format follows Keep a Changelog; versions
follow semantic versioning once the project reaches 1.0.

## [Unreleased]

### Added

- Tabbed rack navigation: Speech, Edit, Shorts, Export, and Providers. Each tab
  shows only the modules and controls that belong to that area.
- A provider/capability panel backed by `GET /api/v1/capabilities` and the
  `videoflow_list_capabilities` MCP tool. External providers are opt-in per run
  and can be blocked globally with `VIDEOWFLOW_ALLOW_EXTERNAL=0`.
- `ProvidersConfig` in project state. `allow_external_services` is persisted and
  forwarded by project runs.
- Short render aspect ratios: `9:16`, `1:1`, and `16:9`. ASS PlayRes and FFmpeg
  dimensions follow the selected aspect.
- Short source window: `shorts_source_start_sec` and `shorts_source_end_sec` in
  the CLI, API, MCP, project config, and UI.
- Duration presets in the Shorts tab and an aspect-aware caption preview.
- Per-Short editor: trim, retitle, aspect/frame size, caption overrides, and
  re-render. The API is `POST /api/v1/jobs/{job_id}/shorts/{index}/edit`, the
  MCP tool is `videoflow_edit_short`, and the rack uses Clip/Captions tabs.
- Prompt-to-Clip and reprompt for Short selection: topic focus, refinement
  context from the previous `shorts.json`, heuristic term boosts, and LLM focus.
  Exposed in CLI, API, MCP, project config, and the Shorts tab.
- Auto hook (`off`, `metadata`, `repeat`, `reorder`) and an explainable 0–100
  virality score with a per-factor breakdown. Hook/score metadata appears in
  `shorts.json` and the rack.
- Short result badges expose the selected aspect, virality score, and hook text.

### Changed

- `scripts/release.py` now keeps only the three newest `releases/v*` folders.
  `--keep N` changes the retention count, and the release output lists every
  pruned folder.
- Release staging is documented as the canonical artifact store. Generated
  `build/`, `dist/`, coverage files, and caches are cleaned after each release.
- MCP now exposes fourteen tools and four resources.

### Docs

- Refreshed the README, module specs, testing notes, UI spec, and operator
  manuals to describe FCPXML audio fades, the caption preview, the tabbed rack,
  provider policy, Short aspect ratios, and the three-release retention policy.

### Verified

- Tests: 331 passed, 11 xfailed, 7 deselected; coverage 99.02%; ruff and mypy
  clean.
- UI: `svelte-check` reports 0 errors and 0 warnings; 13 Vitest tests and the
  production build pass.

## [0.21.2] — 2026-10-21

### Added

- The Shorts card now includes a live 9:16 caption preview. It follows the
  configured font, size, weight, italic/uppercase, primary and karaoke colors,
  outline, shadow, box, alignment, position, and animation.

### Fixed

- FCPXML/Resolve now emits audio fade edges as keyframed `adjust-volume` ramps
  on each `asset-clip`. The ramp uses the clip-relative `keyframeAnimation`
  form required by the FCPXML 1.9 DTD.
- FCPXML sequences declare the enumerated `audioRate` label (`48k`, `44.1k`, ...)
  instead of raw hertz. A generated timeline now validates against the FCPXML
  1.9 DTD.
- All three NLE artifacts now carry audio fades: xmeml transition items,
  Kdenlive volume filters, and FCPXML volume keyframes.

### Verified

- Tests: 315 passed, 11 xfailed, 7 deselected; coverage 99.00%; ruff and mypy
  clean.
- UI: `svelte-check` reports 0 errors and 0 warnings; the production build
  succeeds with 13 Vitest tests.
- Linux and Windows binaries produced six xmeml fade items, a Kdenlive volume
  ramp, and FCPXML that validates against the official 1.9 DTD. Sizes and
  SHA-256 values are in `releases/v0.21.2/` and its `manifest.json`.

## [0.21.1] — 2026-10-21

### Fixed

- Premiere xmeml now writes single-sided `transitionitem` fades for audio
  fade-in and fade-out edges, using the Cross Fade (0 dB) audio transition.
- Kdenlive MLT audio entries now carry a keyframed `volume` filter for the same
  fades. The project still opens as a native `.kdenlive` sequence.
- FCPXML/Resolve fade transitions remain pending; the FCPXML artifact still
  carries the audio offsets but not dedicated fade elements.

### Verified

- Tests: 315 passed, 11 xfailed, 7 deselected; coverage 99.00%; ruff and mypy
  clean.
- Linux and Windows binaries emitted six xmeml audio transition items and a
  Kdenlive volume keyframe ramp. Sizes and SHA-256 values are in
  `releases/v0.21.1/release-notes.md` and `manifest.json`.

## [0.21.0] — 2026-10-21

### Added

- Configurable zoom window: `min_scale`, `max_scale`, and `punch_in_scale` with
  validation and UI/API/MCP controls. The state model no longer hard-codes a
  1.30 maximum.
- Configurable audio fades: `fade_in_ms`, `fade_out_ms`, and `fade_curve` in the
  J/L-cut module, in addition to the existing crossfade and offset.
- Configurable Shorts selection: target count, minimum count, duration window,
  and `auto|llm|heuristic` ranking. The LLM client is created for Shorts even
  when retake culling is off, and the heuristic ranks hook/impact signals rather
  than taking the first windows.
- `videoflow run --shorts` with count/minimum/duration/selection flags, so the
  main project and vertical Shorts are produced together.
- Detailed caption/karaoke style: font family, size, weight, italic, uppercase,
  primary/highlight/outline colors, outline width, shadow color/offset/opacity,
  background box color/opacity/padding, alignment, normalized position, max
  width, animation, and word-timing fallback.
- ASS karaoke generation from word timings, with proportional and sentence
  fallbacks when an engine does not return word timestamps.
- The same caption and Shorts fields are available in the UI rack, job API,
  project config, presets, and MCP overrides. `videoflow_generate_shorts` now
  accepts `min_count` and `selection_mode`.

### Changed

- The setup card now has an explicit “Also render vertical shorts” control, and
  the “Main + Shorts” starting point makes clear that Shorts are additive.
- Shorts report a score and warning when fewer than the configured minimum can
  be selected.
- Audio fade timing/curve is now configurable and stored on the timeline. NLE
  transition elements for those fades remain a follow-up; the current exporters
  still carry the audio cut offsets rather than dedicated crossfade items.

### Verified

- Tests: 315 passed, 11 xfailed, 7 deselected; coverage 99.00%; ruff and mypy
  clean.
- UI: 0 errors/warnings, 13 Vitest tests, production build passed.
- A real source with `--shorts` produced the main project and Shorts MP4s/ASS,
  including word-timed karaoke.
- Linux binary, AppImage, and Windows PE were built and smoke-tested. Sizes and
  SHA-256 values are in `releases/v0.21.0/release-notes.md` and
  `manifest.json`.

## [0.20.1] — 2026-10-20

### Fixed

- DaVinci Resolve FCPXML 1.9/1.10 media references now use the required
  `<media-rep kind="original-media" src="..."/>` child. The old `<asset src>`
  form is FCPXML 1.8-only and could make Resolve reject or offline the timeline.
- Premiere Pro now receives xmeml version 4 with `explodedTracks`, a sequence
  UUID, `file://localhost/` path URLs, a full `<file>` definition on every
  video and audio clipitem, and explicit A/V `<link>` groups. The Basic Motion
  effect id is now `basicmotion`.
- Kdenlive now receives a native `.kdenlive` MLT XML project instead of an OTIO
  file: profile, source chain, video/audio tractors, sequence tractor, bin, and
  final tractor. OTIO remains available as a library helper, not the Kdenlive
  deliverable.

### Changed

- The Kdenlive artifact is `timeline.kdenlive`; the API/MCP target key remains
  `kdenlive`. The historical `write_otio` config key still controls this
  artifact.
- Export tests now assert the media-rep, xmeml full-file/link shape, and native
  MLT structure.

### Verified

- Tests: 310 passed, 11 xfailed, 7 deselected; coverage 99.28%; ruff and mypy
  clean.
- Linux and Windows binaries wrote all three artifacts; each was parsed back as
  FCPXML, xmeml, or MLT XML and checked for its required media links and track
  structure. AppImage smoke passed.
- Sizes and SHA-256 values are in `releases/v0.20.1/release-notes.md` and
  `manifest.json`.
- The three NLE import flows still require a manual gate in Resolve, Premiere,
  and Kdenlive; this environment does not have those applications installed.

## [0.20.0] — 2026-10-20

### Added

- A local filesystem browser for the rack: `GET /api/v1/fs/roots`,
  `GET /api/v1/fs/list`, and `POST /api/v1/fs/mkdir`, with search, file-extension
  filters, hidden-file control, breadcrumbs, writable checks, and a 2,000-entry
  ceiling.
- `GET /api/v1/media/probe`, so selecting a source shows duration, resolution,
  frame rate, audio rate, and size without running the pipeline.
- `PathPicker.svelte` with keyboard navigation, focus trapping, loading, empty,
  and typed error states. It replaces typed source, output, SRT, and model paths
  in the primary flow.
- Source selection suggests `<source-stem>-videoflow` next to the source. The
  output picker can create a folder in place.
- A redesigned project setup: numbered source/output/transcript cards, metadata
  chips, YouTube/Lecture/Shorts starting points, a collapsed advanced section, a
  clear primary action, inline validation, progress details, and transient
  success toasts.
- Pure path helpers for POSIX and Windows basenames, parents, and output
  suggestions, covered by Vitest.

### Changed

- The rack no longer requires typing an absolute path in the normal flow.
  Advanced users can still paste paths under **Advanced paths and local models**.
- The primary action is disabled until both source and output are present, and
  source/output/transcript changes keep the UI state consistent.
- The run summary keeps the same job, artifact, recent-job, inspector, and log
  behavior while adopting the updated visual hierarchy.

### Security

- The browser is restricted to `VIDEOWFLOW_ALLOWED_ROOTS`; symlinks that escape a
  root are omitted or rejected. Directory creation validates a single portable
  segment, including Windows reserved names. No media is uploaded.

### Verified

- Tests: 309 passed, 11 xfailed, 7 deselected; coverage 99.28%; ruff and mypy
  clean.
- UI `check` reports 0 errors and 0 warnings; 13 Vitest tests pass and the
  production build succeeds.
- Frozen Linux UI: selected a real 48 kHz source, showed its metadata, created
  an output folder, ran the pipeline, and wrote all three exports.
- Linux binary, AppImage, and Windows PE were built. Windows `version`, `doctor`,
  `demo`, served filesystem routes, and a real Faster-Whisper run passed under
  Wine. Sizes and SHA-256 values are in
  `releases/v0.20.0/release-notes.md` and `manifest.json`.

## [0.19.0] — 2026-10-20

### Added

- Local Faster-Whisper 1.2.1 transcription through CTranslate2, with the full
  16 kHz WAV sent to the engine, word timestamps required for the quality path,
  and exact floor/ceil conversion from word seconds to source samples.
- `TranscribeConfig.engine` with `auto`, `faster-whisper`, and `whisper.cpp`.
  `auto` prefers Faster-Whisper when the optional package and selected model are
  present, then falls back to whisper.cpp. Explicit engines fail with an
  actionable hint instead of silently downgrading.
- `--whisper-engine`, `--model-size`, `--device`, `--compute-type`,
  `--whisper-vad`, and `--faster-whisper-model` in `videoflow run`; matching job
  API fields, project run options, MCP arguments/overrides, and rack controls.
- Local CTranslate2 model discovery through `VIDEOWFLOW_FASTER_WHISPER_MODEL`,
  the frozen bundle, the executable directory, and the portable home. A model
  directory must contain `model.bin` and `config.json`; models are never
  downloaded implicitly.
- `scripts/fetch_faster_whisper.py` with the pinned
  `Systran/faster-whisper-small` revision
  `536b0662742c02347bc0e980a01041f333bce120`, per-file sizes, and SHA-256
  verification.
- `--with-faster-whisper` and `--refresh-faster-whisper` in the portable build.
  PyInstaller collects Faster-Whisper, CTranslate2, Tokenizers, PyAV, Hugging
  Face Hub, and the ~484 MB small model under `faster-whisper/small/`.
- `doctor` reports the Faster-Whisper package version, resolved model, and
  readiness.
- Unit, contract, CLI, job, API, MCP, runtime, and portable coverage for engine
  selection, fallback, explicit failures, full-WAV calls, exact timestamps, and
  model discovery.

### Changed

- `transcribe` is now an `auto` local quality path. An SRT or project transcript
  still wins, and an ASR base URL still takes precedence over both local engines.
- Transcript sources are reported distinctly as `faster-whisper`, `whisper`,
  `asr`, `srt`, or `project`.
- The optional `faster-whisper` extra pins Faster-Whisper 1.2.1 and PyAV
  `>=11,<19`; PyAV 19 removes the `metadata_errors` argument used by 1.2.1.
- Release builds bundle the model and runtime, so artifacts are substantially
  larger than 0.18.0. A build without the flag keeps the whisper.cpp fallback.

### Verified

- Tests: 301 passed, 11 xfailed, 7 deselected; coverage 99.27%; ruff and mypy
  clean; UI check, Vitest, and production build pass.
- A real 48 kHz source produced a `faster-whisper` transcript with source-sample
  word timings; `auto` selected Faster-Whisper and an explicit whisper.cpp run
  still completed. The frozen Linux API and AppImage quality paths produced the
  same result.
- Linux 0.19.0 binary, AppImage, and Windows PE were built and smoke-tested.
  Windows `version`, `doctor`, `demo`, and a real Faster-Whisper run passed under
  Wine. Sizes and SHA-256 values are in
  `releases/v0.19.0/release-notes.md` and `manifest.json`.

## [0.18.0] — 2026-10-20

### Added

- Silero VAD v5.1.2 as the quality speech detector, running through ONNX
  Runtime on the CPU with 16 kHz mono PCM, 512-sample windows, and the pinned
  `state` tensor carried between windows.
- Typed VAD engine selection: `auto` prefers Silero when the model and
  `onnxruntime` are available, `silero` requires it, and `ffmpeg` forces
  `silencedetect`. Explicit Silero failures are actionable instead of silent.
- Exact floor/ceil rescaling from 16 kHz windows to source sample spans, plus
  speech pads that are applied after retake culling and clamped to the media
  duration.
- `--vad-engine`, `--speech-threshold`, `--speech-pad-before-ms`, and
  `--speech-pad-after-ms` in `videoflow run`; matching job API, project config,
  MCP overrides, and rack fields.
- `vad_engine` in job results, `run.json`, MCP VAD results, project-state
  config, and JSON Schemas; `doctor` reports the model and ONNX Runtime.
- `scripts/fetch_silero.py` with a pinned URL, SHA-256 verification, and
  `vendor/silero/silero_vad.onnx`; `--with-silero` and `--refresh-silero` in
  the portable build. PyInstaller bundles the model and ONNX Runtime.
- Unit, contract, CLI, project, job, runtime, and portable coverage for Silero,
  engine selection, rescaling, pads, fallback, and packaging.

### Changed

- `work/vad.wav` is written at 16 kHz only when Silero runs; `work/source.wav`
  remains at the source rate and FFmpeg remains the portable fallback.
- Release builds now bundle the Silero model. A build without `--with-silero`
  still runs: `auto` falls back to FFmpeg and `silero` fails with a fetch/build
  hint.
- `videoflow demo` explicitly uses FFmpeg so the self-contained demo does not
  depend on the optional VAD model.

### Verified

- Tests: 284 passed, 12 xfailed, 7 deselected; coverage 99.26%; ruff and mypy
  clean; UI check, Vitest, and production build pass.
- Linux 0.18.0 binary, AppImage, and Windows PE were built and smoke-tested,
  including Silero `vad_engine=silero` runs. The PE was validated under Wine.
- Frozen Linux and Windows project and MCP flows passed with Silero and
  revision snapshots `000001` through `000004`.
- Auto fallback was verified with a missing model; explicit Silero failed with
  `ingest_failed` and the fetch/build hint.

## [0.17.0] — 2026-10-20

### Added

- Persistent projects under `<root>/.videoflow/`: a compact registry, atomic
  state writes, monotonically increasing `revision`, and append-only snapshots
  under `revisions/`.
- Project REST routes: create/list/read, media registration, module config and
  enabled flags, full project run, cancel, SSE events, transcript read and
  sentence overrides, exports, and preset application.
- `ProjectState.revision`, starting at 1 and written into every snapshot.
- Project runs preserve `project_id`, module config, enabled flags, transcript
  word timings, manual overrides, export target flags, and FCPXML dialect.
- Operator presets under `$VIDEOWFLOW_HOME/presets/`, with partial-file
  validation, shipped-name shadowing, list/read/write routes, and atomic apply
  to a project.
- Shared SRT formatting in the domain, used by the REST transcript route and
  MCP resources.

### Changed

- `run_portable` and `JobManager` accept project metadata, revision, config,
  enabled flags, and a preloaded transcript; successful project jobs snapshot
  the state they wrote.
- Per-module reruns return typed `501 not_implemented` until the cache-backed
  module runner lands. The full project run is implemented.
- Project media registration and transcript overrides invalidate stale derived
  results instead of leaving old timeline data looking current.
- API docs now describe the implemented project contract and error statuses.

### Verified

- Tests: 269 passed, 13 xfailed, 7 deselected; coverage 99.26%; ruff and mypy
  clean.
- Project route contracts cover create/list/read, media jail, config validation,
  enabled flags, transcript overrides, exports, presets, project runs, events,
  cancellation, and active-job rejection.
- Linux 0.17.0 binary and AppImage plus Windows PE 0.17.0 build and smoke checks
  are recorded in `releases/v0.17.0/release-notes.md`.

## [0.16.0] — 2026-10-20

### Added

- All twelve MCP tools now execute real work. `run_vad` uses FFmpeg speech
  detection; `transcribe` uses local whisper.cpp and stages an SRT;
  `get_transcript`, culling, zoom, J-cut, shorts, and export tools read and
  modify real project state.
- Staged MCP edits: retake culling, zoom configuration, and J-cuts update
  pending options that the next `videoflow_run_pipeline` applies unless the
  caller explicitly overrides them.
- `videoflow_generate_shorts` returns deterministic vertical clip proposals
  from the cached or project transcript, with retake cuts respected.
- `videoflow_export_fcpxml` exports the latest completed state for Resolve,
  Premiere, or Kdenlive, warns when staged edits are pending, and writes any
  requested output path inside the allowed roots.
- All four MCP resources are live: project state, transcript SRT, presets, and
  export paths. Missing data returns typed errors instead of stubs.
- `videoflow_transcribe` writes its SRT into the target project and stages it,
  so the pipeline uses the exact transcript the agent inspected.

### Changed

- `videoflow_run_vad` takes `noise_db`, `min_silence_ms`, and `min_speech_ms`,
  matching the FFmpeg backend.
- Loading a different source clears the previous MCP job, transcript, pending
  edits, and output context.
- Word-level retake culling returns `word_overrides_not_supported`; sentence
  ids remain the supported granularity.
- MCP documentation and the agent manual now describe the live contract.

### Verified

- Real MCP end-to-end on `jfk.mp4`: load, VAD, local transcription, transcript,
  culling, zoom, J-cut, shorts, pipeline success, all resources, and export.
- Linux 0.16.0 binary and AppImage: `version`, `doctor`, `demo`, and a frozen
  MCP workflow with local whisper.cpp.
- Windows PE 0.16.0 under Wine: `version`, `doctor`, `demo`, and a frozen MCP
  workflow with local `whisper-cli.exe`.
- Tests: 243 passed, 15 xfailed, 7 deselected; coverage 99.22%; ruff and mypy
  clean.

## [0.15.0] — 2026-10-20

### Added

- Offline transcription through the bundled whisper.cpp CLI and a tiny GGML
  model. `--transcribe` with no ASR URL extracts 16 kHz audio and runs locally.
- `whisper_model` in the job API, MCP overrides, and the Transcribe card; an
  empty value uses `ggml-tiny.bin`, a path selects a larger model.
- `scripts/fetch_whisper.py` builds Linux `whisper-cli` from pinned v1.7.6
  source and downloads the official Windows x64 build plus the tiny model.
- `scripts/build_portable.py --with-whisper` bundles the CLI and model.
- Runtime discovery through `VIDEOWFLOW_WHISPER_BIN` and
  `VIDEOWFLOW_WHISPER_MODEL`, with bundled `whisper/` paths as defaults.

### Changed

- ASR URL remains the opt-in remote path; an empty URL now means local
  whisper.cpp instead of a configuration error.
- Portable binaries grow by roughly 80 MB for the CLI and tiny model.

### Verified

- Real Linux `whisper-cli` and Windows `whisper-cli.exe` under Wine transcribe a
  16 kHz WAV to SRT; the adapter parses it into source-sample sentences.

## [0.14.1] — 2026-10-20

### Fixed

- Duration badges show milliseconds under one second instead of `0:00`.
- Header and footer no longer claim Shorts is CLI-only.
- Added a favicon, removing the `/favicon.ico` 404.

### Verified

- Real Chrome session: load, fill paths, enable culling, run, 7 per-block
  progress bars at 100%, global log with 53 lines, keep override, apply, second
  job succeeded. No console errors, request failures, or 4xx/5xx responses.

## [0.14.0] — 2026-10-20

### Added

- Speech-to-text through an OpenAI-compatible `/audio/transcriptions` endpoint,
  with `verbose_json` segments and optional word timings.
- `transcribe`, `asr_base_url`, `asr_model`, and `asr_language` on the job API,
  MCP overrides, and the Transcribe card.
- ASR key stays in `VIDEOWFLOW_ASR_API_KEY`; base URL falls back to
  `VIDEOWFLOW_ASR_BASE_URL`.
- SRT still wins when both a transcript and ASR are configured.
- `transcript_source` in the job report (`srt`, `asr`, or `none`).
- Unit tests for the HTTP client and an end-to-end ASR job.

### Changed

- Version is 0.14.0.
- The Transcribe card is enabled and configurable; local Faster-Whisper is still
  a future adapter.

### Verified

- Fake OpenAI-compatible ASR: 3 segments, `transcript_source=asr`, 3 timeline
  segments, stage `transcribe` succeeded.

## [0.13.0] — 2026-10-20

### Added

- Manual sentence overrides: `POST /api/v1/jobs` accepts `overrides` with
  `sentence_id` and `action` (`keep` or `discard`).
- Overrides are applied after the retake guard, so an editor can keep a culled
  take or discard a kept one. A manual decision wins.
- The inspector lists transcript sentences with Keep/Discard controls and an
  Apply overrides action that starts a new job with the same configuration.
- `manual_override_count` in the job report.
- MCP `overrides` support and unit/API tests.

### Changed

- Version is 0.13.0.

### Verified

- Base cull: 2 segments, 1 cull.
- Keep override: 3 segments, 0 culls, 1 override.
- Discard override: 2 segments, 1 cull, 1 override.

## [0.12.0] — 2026-10-20

### Added

- Shorts run as part of a job: selection, retake-aware conforming, ASS captions,
  1080x1920 MP4 render, a `shorts` stage with progress/logs, and `shorts.json`.
- `POST /api/v1/jobs` accepts `shorts`, `shorts_count`, `shorts_min_sec`,
  `shorts_max_sec`, and `shorts_subtitles`.
- `GET /api/v1/jobs/{id}/shorts/{index}` downloads a rendered vertical clip.
- The Shorts card is configurable and enabled when an SRT is present; the run
  summary lists shorts with download links.
- MCP overrides accept the shorts fields.
- API/journal tests and a real media job with two shorts.

### Changed

- Version is 0.12.0.

### Verified

- Live API job: 7 stages, export + shorts; two 1080x1920 MP4s; short download 200.
- AppImage/Windows PE rebuilt with the Shorts card and telemetry.

## [0.11.0] — 2026-10-20

### Added

- Per-stage telemetry: status, progress, start/finish timestamps, duration, and
  messages for ingest, VAD, SRT import, retakes, J/L cuts, zooms, and export.
- Bounded job logs with module/level filters and a download endpoint. FFmpeg
  commands and the last 50 stderr lines are captured; `job.log` is written to the
  output directory.
- API fields for VAD/pads, J/L offsets, zoom mode/scale/anchor/pan, retake
  strictness/strategy/window, LLM URL/model, and export targets.
- New rack UI: per-block progress, date/duration, status icons, global/per-block
  log drawer, configurable cards, recent jobs, and a run summary.
- Vitest coverage for date/duration/status formatting.
- `GET /api/v1/jobs/{id}/logs` and `?download=1`.

### Changed

- Version is 0.11.0.
- Job timestamps use millisecond precision, so short runs report real durations.

### Verified

- API job reports all stages with durations and logs.
- AppImage and Windows PE rebuilt with the new UI and telemetry.

## [0.10.0] — 2026-10-20

### Added

- Vertical shorts engine: deterministic or LLM sentence selection, retake-aware
  conforming, 1080x1920 H.264/AAC render, and ASS captions.
- `videoflow shorts INPUT --transcript subs.srt -o DIR` with count, duration
  bounds, subtitle toggle, culling, and optional OpenAI-compatible selection.
- `FFmpegAdapter.render_short` with concatenated pieces, center crop, and libass
  burn-in.
- ASS timing/text escaping and source-to-output subtitle mapping.
- Unit and real-media tests for selection, culls, LLM validation, ASS, CLI, and
  vertical output dimensions.

### Changed

- Version is 0.10.0.

### Verified

- Media test renders two 1080x1920 shorts with subtitles from a generated
  fixture.
- Frozen Linux binary and Windows PE (Wine) include the `shorts` command.

## [0.9.1] — 2026-10-20

### Fixed

- AppImage no longer exits immediately when opened without arguments. AppRun now
  starts `serve --open`, keeps the server running, and opens the rack UI.
- `videoflow serve --open` schedules the browser at the correct loopback URL,
  including when bound to `0.0.0.0` or `::`.
- AppImage builds can run `--appdir-only` for contract tests without
  appimagetool.

### Added

- AppDir contract tests for AppRun, desktop entry, icon, and executable bits.
- `scripts/smoke_appimage.py` and a `packaging` pytest marker for a real
  AppImage: version, doctor, demo, extract-and-run fallback, and serve health.

### Changed

- Version is 0.9.1.

## [0.9.0] — 2026-10-20

### Added

- `POST /api/v1/jobs` accepts `transcript` (SRT path) and `cull_retakes`.
  Transcript paths go through the same allowlist as media.
- `GET /api/v1/jobs/{id}/state` returns the project state for the UI inspector.
- The rack UI takes an optional SRT, enables retake culling, and shows culled
  sentences and guard restorations from the job state.
- MCP `videoflow_run_pipeline` overrides accept `transcript`, `cull_retakes`,
  `strictness`, `retake_strategy`, and `context_window`.
- Release artifact names include the version:
  `videoflow-0.9.0-linux-x86_64`, `VideoFlow-0.9.0-x86_64.AppImage`,
  `videoflow-0.9.0-windows-x86_64.exe`.

### Changed

- Version is 0.9.0.
- The job manager builds an LLM client from `VIDEOWFLOW_LLM_BASE_URL`,
  `VIDEOWFLOW_LLM_MODEL`, and `VIDEOWFLOW_LLM_API_KEY` when culling is enabled.

### Verified

- API test for transcript options, path jail, and state output.
- UI `npm run check` and `npm run build` are clean.

## [0.8.0] — 2026-10-20

### Added

- Linux AppImage builder (`scripts/build_appimage.py`) wrapping the onefile
  binary, with an icon, desktop entry, and AppRun.
- Portable Linux data directory next to the AppImage (`APPIMAGE` aware).
- Windows PE build path without GitHub Actions: Wine WoW64 + Windows embeddable
  Python + PyInstaller, with Windows FFmpeg binaries.
- `release.py` stages multiple artifacts, checksums, and a manifest.
- Releases now include Linux binary, AppImage, and Windows `.exe`.

### Changed

- Version is 0.8.0.
- GitHub Actions workflows removed. Builds and smoke tests are local.
- `packaging/videoflow.spec` accepts `VIDEOWFLOW_VENDOR_DIR` for cross-OS
  binaries.

### Verified

- AppImage: `doctor` and `demo`, three exports, bundled FFmpeg.
- Windows PE under Wine: `version`, `doctor`, `demo`, three exports, bundled
  FFmpeg.
- Both artifacts are staged in `releases/v0.8.0/`.

## [0.7.0] — 2026-10-19

### Added

- `GET /api/v1/jobs/{id}/artifacts/{target}` serves a generated timeline for
  download, confined to the job output directory.
- UI artifact cards are download links.
- Quick presets in the portable panel: YouTube, Lecture, Shorts.

### Changed

- Version is 0.7.0.

### Verified

- API contract test for in-output downloads and unknown artifacts.
- `npm run check` and `npm run build` are clean.

## [0.6.0] — 2026-10-19

### Added

- SRT transcript import with exact sample-time conversion.
- OpenAI-compatible JSON client: Ollama, LM Studio, Groq, and other
  `/chat/completions` endpoints; temperature 0; response-format fallback; no key
  in errors.
- Transcript-driven retake culling with overlapping context windows, strict id
  validation, exact-repeat fallback, and the `keep_last`/`keep_best` guard.
- `videoflow run --transcript subs.srt --cull-retakes`, optional LLM via
  `--llm-base-url`, and strictness/strategy/window flags.
- Transcript and retake decisions are persisted in `project_state.json` and
  reported in `run.json`.
- `--min-speech-ms` removes sub-100 ms blips left by codec edges.
- Tests for SRT parsing, LLM transport, chunking, guard restoration, interval
  subtraction, and the culling pipeline.

### Changed

- Version is 0.6.0.
- The LLM adapter is now a real implementation; its contract xfail is removed.

### Verified

- Frozen Linux binary: `--transcript` + `--cull-retakes` culls an exact repeat.
- Frozen Linux binary against a local OpenAI-compatible server: the model
  discards both attempts, the guard restores the last one, and the run reports
  one cull plus one restoration.

## [0.5.0] — 2026-10-19

### Added

- The SvelteKit rack starts real portable jobs: source/output fields, silence
  and zoom options, live progress, cancel, artifact paths, and typed errors.
- Module cards reflect live job stages. Neural modules are marked `later` and
  render as bypassed.
- Typed API client (`ui/src/lib/api.ts`) for system info and jobs.
- `releases/` policy, a `scripts/release.py` staging tool, checksums, manifests,
  and notes per version.
- Tag builds attach Linux and Windows binaries to the GitHub Release.

### Changed

- Version is 0.5.0.
- The served UI is no longer a static-only shell; it drives the portable API.

### Verified

- `npm run check` and `npm run build` are clean.
- The frozen binary serves the new UI, and the browser page is produced from the
  bundle.

## [0.4.0] — 2026-10-19

### Added

- `JobManager`: in-process jobs with queued/running/succeeded/failed/cancelled
  states, progress, cancellation between stages, bounded concurrency, and history
  pruning.
- REST routes: `POST /api/v1/jobs`, list, get, cancel, per-job SSE, and
  `/api/v1/system`.
- Path allowlist on HTTP and MCP inputs through `VIDEOWFLOW_ALLOWED_ROOTS`,
  defaulting to home, cwd, and the portable data directory.
- Live MCP tools: `videoflow_load_media`, `videoflow_run_pipeline`,
  `videoflow_get_job`, and `videoflow_cancel_job` now call the real pipeline.
  `run_pipeline` accepts optional `source` and `output`.
- Pipeline progress stages: probe, extract, VAD, timeline, export, state.
- Job and API contract tests, plus a real-media API job test.

### Changed

- Version is 0.4.0.
- `create_app` owns the API routes; `create_http_app` adds MCP and the static UI.
- `videoflow serve` now exposes a working job API, not only health.

### Verified

- Frozen Linux binary: POST job → poll → succeeded with three artifacts; SSE
  returns the terminal state; MCP stdio `load_media → run_pipeline → get_job`
  produces three artifacts.

## [0.3.0] — 2026-10-19

### Added

- Unified `videoflow` CLI: `run`, `serve`, `mcp`, `doctor`, `demo`, `version`.
- Model-free speech detection with FFmpeg `silencedetect`, including a parser and
  complement calculation.
- Portable pipeline service: probe, PCM, speech detection, timeline, three
  exports, `project_state.json`, and `run.json`.
- Portable runtime: data directory next to the executable, `VIDEOWFLOW_HOME`,
  binary discovery from the bundle, sibling files, then `PATH`.
- PyInstaller onefile spec, build script with FFmpeg bundling, and a Linux/Windows
  CI matrix with smoke tests.
- Static rack UI served by `videoflow serve` when the UI was built.
- MCP no-trailing-slash redirect (`/mcp` → `/mcp/`).

### Changed

- Version is 0.3.0.
- The API app can mount the built UI at `/`.
- Documentation adds a portable manual and ADR-0010.

### Verified

- Linux onefile (168 MB with static FFmpeg) runs with `PATH` empty: bundled
  FFmpeg and FFprobe are found, `doctor` passes, `demo` produces three artifacts,
  `serve` answers `/health`, `/`, and `/mcp/`, and MCP stdio lists twelve tools.
- Windows is built and smoke-tested in the CI matrix; no Windows binary was
  produced in this Linux workspace.

## [0.2.0] — 2026-10-19

### Added

- FFprobe ingest with rational frame rate, frame count, dimensions, and audio
  sample rate. Missing or unreadable sources fail with `ingest_failed`.
- PCM extraction to 16 kHz mono WAV with atomic replacement and SHA-256 digest.
- Deterministic timeline builder: span normalisation, frame coverage,
  sample-aligned audio, J/L-cut boundary shifts with handle checks, fade metadata,
  and alternating punch-in/pan transforms.
- FCPXML 1.9/1.10 writer with `audioStart`/`audioDuration` for J/L-cuts and
  `adjust-transform` for zoom.
- xmeml (FCP 7 XML) writer with separate video and audio tracks and a Basic
  Motion filter.
- OTIO writer with V1/A1 tracks for Kdenlive 25.04+.
- `export_timeline` service that writes all three artifacts from one validated
  timeline.
- Real-FFmpeg media tests for generated fixtures.
- Timeline builder and exporter contract tests.

### Changed

- Version is 0.2.0.
- Coverage gate now includes the deterministic timeline builder.
- Media, slow, and manual tests are excluded from the default pytest run. Run
  them with `-m media --no-cov`.

### Known gaps

- Audio transitions are not emitted in the NLE artifacts yet; the fade samples are
  recorded in state and the AC-01 contract remains xfail.
- Progressive zoom is stored as metadata but not emitted as keyframes.
- Neural engines, jobs, project routes, SSE, live MCP results, MP4 render, and the
  interactive rack are still stubs.

## [0.1.0] — 2026-10-19

### Added

- English normative product requirements, architecture, data model, timebase,
  pipeline, cache, security, and test plan.
- Specifications for all eight rack modules, the REST API, the MCP server, the
  rack UI, and the three NLE exporters.
- Nine ADRs covering rational time, hexagonal boundaries, secrets, NLE dialects,
  MCP transports, XML building, the retake guard, CPU-first defaults, and the
  single-user runtime.
- User, operator, developer, MCP agent, NLE import, and testing manuals.
- Pydantic project state, module configs, presets, job and error models.
- Committed JSON Schemas generated from the models.
- Rational `Timebase` with frame coverage, pads, and exact round-trips.
- Cache canonicalization and module hashing without mtime.
- Run planning with upstream-dirty rules and bypass handling.
- Retake keeper guard, exact repetition clustering, and restoration records.
- Path allowlist jail, secret redaction, and timeline overlap checks.
- FastAPI health endpoint and MCP Streamable HTTP mount.
- MCP SDK server with twelve tools and four resources, returning structured
  `not_implemented` results.
- Three shipped presets: `youtube-talking-head`, `shorts-aggressive`,
  `lecture-clean`.
- 107 passing unit/contract tests, 21 strict xfails for unbuilt engines, and
  99% coverage on the pure core.
- SvelteKit and Tailwind rack scaffold with the eight module cards.
- CI workflow for tests, coverage, lint, and types.

### Changed

- The Portuguese brief moved to `docs/origin/prd-pt.md` and is non-normative. The
  old `requirements.txt` name was removed because Python treats it as a
  dependency list.
- FCPXML is no longer claimed as a Premiere import format. Premiere receives
  xmeml; Kdenlive receives OTIO.
- Neural defaults are CPU/int8/small, not CUDA/float16/large-v3.
- Authoritative time is rational frames and samples, not float seconds.

### Known gaps

- Media engines, exporters, job execution, project routes, SSE, and the live rack
  are specified and stubbed.
- No license has been chosen.
- No face tracking in v1.
- The NLE compatibility spike and long-file manual QA are not yet executed.

### Security

- Secrets are names in state and values only in the environment or a mode-0600
  file.
- The API binds to loopback and CORS is limited to the local UI.
