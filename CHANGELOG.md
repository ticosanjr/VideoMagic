# Changelog

All notable changes are recorded here. Format follows Keep a Changelog; versions
follow semantic versioning once the project reaches 1.0.

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
