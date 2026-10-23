# Changelog

All notable changes are recorded here. Format follows Keep a Changelog; versions
follow semantic versioning once the project reaches 1.0.

## [0.44.0] - 2026-10-23

### Added

- **Second-source audio mix.** `shorts.render.mix_second_audio` mixes the second
  split-screen source with the primary audio, with a UI checkbox.
- **Stable Pexels cache.** Stock downloads are keyed by the source URL hash, so
  repeated plans reuse the same file instead of re-downloading.
- B-roll plan remains auditable with provider, license, attribution, and source
  URL.

### Notes

- The second source is still operator-supplied; face detection and automatic
  source assignment remain future work.
- pyannote and Pexels still need real model/API validation.
- 445 Python tests, 14 Vitest tests, and 8 Playwright tests pass.

## [0.43.0] - 2026-10-23

### Added

- **Inline recipe nodes.** Each node expands into schema-derived fields with
  labels, descriptions, validation, enums, booleans, numbers, colors and path
  pickers.
- **Saved canvas.** Recipe JSON carries optional `ui` layout metadata:
  positions, expanded/pinned state, width, and viewport. UI-only changes do not
  invalidate checkpoints.
- **Autosave layout.** Dragging or pinning a node saves the recipe layout after a
  short debounce. `Auto layout` resets positions.
- **Per-step progress.** `StepIO` reports local progress; jobs expose
  `step_progress`; each node shows state and percentage.
- **Field validation.** Drafts remain editable, but Run is blocked while fields
  have errors. Server validation remains authoritative.
- Playwright coverage for saved inline layout and direct node edits.

### Notes

- 445 Python tests, 14 Vitest tests, and 8 Playwright tests pass.

## [0.42.0] - 2026-10-23

### Added

- **MLT/Kdenlive render smoke.** `scripts/melt_check.py` renders a generated
  Kdenlive/MLT project with `melt` and returns a JSON verdict.
- A media test builds a real two-cut project, exports Kdenlive, and renders it
  with `melt` when available.
- CI installs `melt` and runs the media suite.
- Final Windows, AppImage, Linux, and SBOM assets are produced by the tag
  release workflow.

### Notes

- The exact Kdenlive cross-dissolve remains a limitation; the generated project
  uses affine opacity/volume fades.
- Manual Resolve/Premiere/Kdenlive import QA remains pending.
- 443 Python tests, 8 media tests, 14 Vitest tests, and 6 Playwright tests pass.

## [0.41.0] - 2026-10-23

### Added

- **Inline preview.** MP4 artifacts render in the recipe result panel, and
  rendered Shorts get video previews.
- **Artifact serving API.**
  - `GET /api/v1/jobs/{id}/artifacts/{name}`.
  - `GET /api/v1/jobs/{id}/shorts/{index}/file`.
  - Both paths are constrained to the job output directory.
- API tests for artifact and Short file serving.

### Notes

- Previews use the rendered file; there is no low-res proxy yet.
- 443 Python tests, 14 Vitest tests, and 6 Playwright tests pass.

## [0.40.0] - 2026-10-23

### Added

- **Job persistence.** `JobManager` writes each job as JSON under the VideoFlow
  home and reloads it on restart. Queued/running jobs become `failed` with
  `job_interrupted`, so the API never reports a dead job as live.
- **Batch resume.** `POST /api/v1/batches/{id}/resume` and the batch modal
  restart failed/cancelled batches, skipping items already succeeded.
- **Shared persistence pattern** for jobs and batches: atomic JSON writes,
  restart reload, interrupted-state recovery.
- Tests for job restart, interrupted jobs, and batch resume.

### Notes

- The legacy `PipelineRunner.execute` contract remains an xfail; planning is
  live, and the recipe engine is the execution path.
- 442 Python tests, 14 Vitest tests, and 6 Playwright tests pass.

## [0.39.0] - 2026-10-23

### Added

- **Tag-driven release workflow.** `v*` tags build Linux, AppImage, and Windows
  artifacts, generate an SBOM, stage checksums, and publish the GitHub release.
- **Windows smoke test.** The Windows runner executes `version`, `doctor`, and
  `demo` before uploading the executable.
- **Media tests in CI.** `pytest -m media --no-cov` now runs on Ubuntu.
- **SBOM.** `scripts/generate_sbom.py` writes a CycloneDX-style JSON SBOM; the
  release includes `sbom.json`.
- **Automatic retention.** Successful recipe runs prune checkpoints beyond 200
  and run history beyond 30. Opt out with `VIDEOWFLOW_PRUNE_AFTER_RUN=0`.
- Fixed the media API test to force the FFmpeg VAD path instead of depending on
  Silero's speech classification.

### Notes

- 439 Python, 14 Vitest, and 6 Playwright tests pass.
- Media suite: 7 passing.

## [0.38.0] - 2026-10-23

### Added

- **Two-source split-screen.** `shorts.render.second_source_path` renders the
  left panel from the main source and the right panel from a second angle.
  Without a second source, the same-source two-panel layout remains.
- UI control and file picker for the second split-screen source.
- Repository policy test: project configuration and test data are JSON; only
  GitHub Actions workflows may be YAML.
- Playwright coverage for the second-source control.
- Final Windows PE workflow run and release attachment.

### Notes

- Exact Kdenlive cross-dissolve is still not validated; Kdenlive uses the
  affine opacity/volume transition fades.
- Manual Resolve/Premiere/Kdenlive import QA remains pending.
- 439 Python tests, 14 Vitest tests, and 6 Playwright tests pass.

## [0.37.0] - 2026-10-22

### Added

- **Schema-driven inspector.** Primitive parameters are rendered from each
  step's `params_schema` (boolean, number, enum, text), not only from the
  hand-written quick controls.
- **NLE validation in the UI.** A Validate action calls
  `POST /api/v1/exports/validate` and shows per-format status, counts, errors,
  and warnings.
- **B-roll plan viewer.** Job results expose `broll_plan`, and the UI shows the
  provider, license, and path for each planned clip.
- **Persistent batch history.** Batch JSON is written to the VideoFlow home,
  reloaded on restart, and interrupted batches are marked failed.
- Playwright now covers schema fields and the NLE validation modal.
- JSON-only configuration policy documented for project data and tests.

### Notes

- GitHub Actions still uses YAML because the platform requires it.
- 437 Python tests and 5 Playwright tests pass.

## [0.36.0] - 2026-10-22

### Added

- **Schema gates.** Recipes and project state now pass through explicit
  `schema_version` migration functions. Missing optional fields in older recipe
  JSON are filled before validation; future versions fail with a typed error.
- **Output maintenance.** `prune_output` removes old checkpoints beyond a keep
  count, stale B-roll cache files, and trims run history.
- CLI: `videoflow recipe cache prune --output ... --keep-steps ... --keep-runs ...`.
- API: `POST /api/v1/maintenance/prune`.
- Tests for migrations, malformed/future versions, checkpoint pruning, history
  trimming, and dry runs.

### Notes

- Checkpoints are still output-local and can be rebuilt; pruning never touches
  source media or export artifacts.
- 434 Python tests pass.

## [0.35.0] - 2026-10-22

### Added

- **Failed-run diagnostics.** Recipe failures write `work/failure.json` with the
  stage, error payload, FFmpeg command, stderr tail, and the last 200 log lines.
- **Failed runs in history.** `run-history.json` now records `failed` and
  `cancelled` runs with their error, so the UI survives restarts and shows them.
- **Playwright E2E.** Installed `@playwright/test`, added a JSON reporter, and
  covered the recipe graph, inspector transition controls, step palette, and
  persisted run-history browser.
- Refactored job history recording into one path for success, failure, and
  cancellation.
- `docs/testing.md` now reflects CI and Playwright.

### Notes

- GitHub Actions still needs a Playwright step; this release wires the local
  command and JSON report first.
- 427 Python tests, 14 Vitest tests, and 3 Playwright tests pass.

## [0.34.0] - 2026-10-22

### Added

- **NLE structural validation.** `scripts/validate_nle.py` and
  `POST /api/v1/exports/validate` parse FCPXML, XMEML, and Kdenlive exports and
  report clips, transitions, keyframes, effects, and affine filters.
- **Manual NLE checklist** in `docs/nle-qa.md`.
- **Legacy module rerun.** The project module route plans the rack graph,
  returns a cached no-op, or starts the full project pipeline. It no longer
  returns `501`.
- **Windows PE in releases.** The Windows workflow downloads a PE32+ x86-64
  executable and the release script attaches it when present.
- CI can be dispatched manually and runs Python and UI checks.

### Notes

- The legacy module route reruns the full graph; it does not yet execute one
  module in isolation. Recipe steps remain the checkpointed path.
- Resolve, Premiere, and Kdenlive are not installed here, so manual import QA is
  still pending. Automated XML validation passes.
- The Windows binary is unsigned; SmartScreen may warn.
- 426 Python tests and 14 UI tests pass.

## [0.33.0] - 2026-10-22

### Added

- **Optional model-based diarization.** `audio.diarize` supports
  `method: "pyannote"` with `model_path`, `device`, and an HF token environment
  variable. It falls back to the pause heuristic by default.
- **Pexels B-roll provider.** `broll.plan` can search and download portrait
  stock clips using `PEXELS_API_KEY`; local assets remain the default.
- **Dialogue split-screen.** `shorts.reframe` marks multi-speaker clips for the
  two-panel layout, and the renderer supports per-panel focus and zoom.
- B-roll plans now include provider, license, attribution, and source URL.
- UI controls for pyannote, Pexels, dialogue split, and panel focus/zoom.
- Optional `diarization` dependency extra.

### Notes

- Pyannote is not installed in this build; the adapter is lazy and tested with a
  fake pipeline plus the heuristic fallback.
- Pexels is opt-in and requires an API key; local B-roll remains fully offline.

## [0.32.0] - 2026-10-22

### Added

- **Kdenlive transforms and keyframes.** Video entries receive an MLT `affine`
  filter with static geometry or `transition.rect` keyframes.
- **Kdenlive transition fades.** Clip transitions add opacity keyframes and
  volume ramps in the MLT project.
- **Recipe inspector quick controls** for transition frames/type, progressive
  zoom, speaker turns, B-roll directory, split-screen, B-roll application, and
  caption speaker colors.
- **Run history browser** in the Recipes tab, with persisted runs and comparison.
- **Piper provider controls** in the Short editor, with binary and model path.
- README, exporter docs, and capability status updated.

### Notes

- Kdenlive crossfades are emitted as opacity/volume fades rather than a validated
  exact cross-dissolve; Kdenlive itself is not available on this build host.
- 419 Python tests and 14 UI tests pass.

## [0.31.0] - 2026-10-22

### Added

- **Heuristic speaker turns.** `audio.diarize` assigns speaker ids by pause
  length. Captions use `CaptionStyle.speaker_colors` for per-speaker colors.
- **Local B-roll.** `broll.plan` matches files in a local asset directory to
  selected Shorts and writes `broll.json`; `shorts.render` applies full-frame
  B-roll overlays.
- **Split-screen Shorts.** `shorts.render` accepts `split_screen` and renders a
  two-panel vertical frame.
- **Local Piper TTS.** The voice-over route accepts `provider: "piper"` with a
  binary and voice model path, in addition to OpenAI-compatible TTS.
- Capability manifest entries for transitions, speaker turns, B-roll,
  split-screen, and local TTS.

### Notes

- Diarization is heuristic, not model-based speaker identification.
- B-roll is local-asset matching, not a stock-video search service.
- Kdenlive parity for transforms and transitions remains pending.

## [0.30.0] - 2026-10-22

### Added

- **Persistent run history.** Successful recipe runs append a compact record to
  `<output>/work/run-history.json`; `GET /api/v1/runs?output=...` exposes it.
  The comparison modal uses this history, so it survives a server restart.
- **GitHub Actions CI.** Linux tests and UI checks run on push and pull request.
- **Windows portable build workflow.** A `windows-latest` workflow builds and
  uploads `videoflow.exe`.
- **Optional onedir build.** `scripts/build_portable.py --onedir` uses PyInstaller
  `COLLECT` instead of a onefile executable.

## [0.29.0] - 2026-10-22

### Added

- **Clip transitions.** `VideoSegment.transition_out` carries a
  `Transition` with `crossfade` or `fade_to_black`, duration, and audio flag.
- `edit.timeline` accepts `transition_frames` and `transition_type`.
- **FCPXML** emits a `transition` element between clips.
- **XMEML** emits a video `transitionitem` with Cross Dissolve/Fade to Black.
- **MP4** uses `xfade`/`acrossfade` for crossfades and video/audio fades for
  fade-to-black.
- Project-state schema updated for transitions.

### Notes

- Kdenlive does not apply clip transforms or per-cut transitions yet.
- The transition duration reduces the MP4 duration for crossfades because the
  clips overlap, as expected.

## [0.28.0] - 2026-10-22

### Added

- **Progressive zoom keyframes.** `Transform` now carries normalized scale
  keyframes. `progressive_zoom` generates two smooth keyframes (minimum scale
  to punch-in scale) for alternating clips.
- **FCPXML keyframes.** `adjust-transform` emits a keyframed `scale` parameter
  with clip-relative rational times.
- **XMEML keyframes.** Basic Motion scale emits `keyframe` entries with
  clip-relative frame positions.
- **MP4 keyframes.** The direct renderer uses `zoompan` for clips with
  keyframes, keeping the output dimensions stable.
- Project state schema updated for `TransformKeyframe`.

### Notes

- Kdenlive does not apply clip transforms yet, so keyframes are not represented
  there.
- Transitions between clips remain the next editing pass.

## [0.27.0] - 2026-10-22

### Added

- **Run comparison.** After a successful recipe run, the UI finds the previous
  successful job for the same output and recipe and offers a comparison modal.
  It shows duration, cached/executed counts, warnings, and a per-step table with
  previous/current status and elapsed milliseconds.
- The comparison uses the normal job history; no new persistent store is
  required.

### Notes

- Keyframed progressive zooms and video transitions remain the next creative
  editing pass. This release focuses on run observability.

## [0.26.0] - 2026-10-22

### Added

- **Direct main-timeline MP4 render.** `export.nle` accepts `mp4` as a target.
  The exporter builds a filter graph from the validated timeline, applies
  J/L-cut audio ranges, fades, and static transforms, and writes H.264/AAC with
  `+faststart`. The legacy job form and recipe editor expose the target.
- **Folder batches.** `videoflow recipe batch`, `POST /api/v1/batches`,
  `videoflow_run_batch`, `videoflow_get_batch`, and `videoflow_cancel_batch`
  process a folder one file at a time. Each item is a normal job with its own
  output folder, progress, cancellation, logs, and recipe checkpoints.
- **Batch UI.** The Recipes tab has a **Batch** modal with folder pickers,
  recursive mode, extension filter, item-level progress, and cancel.
- **Capability manifest entries** for direct MP4 and folder batches.

### Changed

- `ExportParams.targets` and `NewJobRequest.export_targets` accept `mp4`.
- `FFmpegAdapter.render` is implemented with a one-hour render timeout.
- Built-in recipe validation now enforces required upstream step types.

### Validation

- 405 Python tests passed; 14 UI tests passed.
- Real FFmpeg media rendered through the timeline filter graph and was probed
  back at the source dimensions.
- A two-file batch completed both items into separate output folders.

## [0.25.0] - 2026-10-22

### Added

- **Per-step checkpoints.** Every successful recipe step writes
  `work/steps/<id>/manifest.json` and `snapshot.json`. A fingerprint covers the
  step type/version, validated parameters, source fingerprint, and upstream
  step hashes. Matching steps are reused across runs in the same output
  directory, and file-producing steps verify that their outputs still exist.
- **Step-scoped runs.** `POST /api/v1/steps/{step_id}/run`,
  `videoflow recipe step ...`, and the MCP tool `videoflow_run_step` execute a
  step and its dependency closure, then stop.
- **Resume controls.** `videoflow recipe run|step --force` ignores
  checkpoints; the Recipes Config modal has a reuse-checkpoints switch.
- **Per-node execution state.** The graph shows cached, executed, running, and
  failed nodes. The inspector has **Run to here**.
- **Step run reporting.** Job results and `run.json` expose `step_runs` with
  status, elapsed time, fingerprint, and outputs.
- **Dependency validation.** Recipes are rejected when a step's declared
  upstream types are missing, preventing steps from running with absent VAD or
  transcript context.

### Fixed

- `retakes.cull` now explicitly requires `audio.vad` in addition to the
  transcript, so partial runs cannot subtract culls from empty speech.
- Built-in Shorts recipes place NLE export after Shorts rendering.

## [0.24.0] - 2026-10-22

### Added

- **Independent Shorts steps.** `shorts.select`, `shorts.reframe`,
  `shorts.captions`, and `shorts.render` are separate nodes. Reframe tracking
  and ASS caption generation no longer happen inside selection/render.
- **Recipe analysis cache.** `audio.vad` and local/HTTP `transcribe` results are
  cached by source PCM digest plus step parameters under
  `<videoflow-home>/cache/recipe-v1/`. The cache is shared across output
  directories. `videoflow recipe cache path|clear` inspects or clears it;
  `VIDEOWFLOW_RECIPE_CACHE=0` disables it.
- **Cache hit/miss reporting.** `run.json`, job results, and `PipelineContext`
  expose `cache_hits` and `cache_misses`.
- **Full-width recipe canvas.** The Recipes tab now spans the whole content
  area and hides the legacy run-summary sidebar while active.
- **Collapsible recipe controls.** The step inspector is an overlay that opens
  on node click; the step palette is a filterable popover; recipe settings and
  the full recipe/step JSON editor are modal dialogs with a large text area.

### Changed

- The built-in Shorts recipes now run `shorts.reframe` and `shorts.captions`
  explicitly before `shorts.render`.
- `shorts.select` no longer tracks faces. If a recipe sets a non-center
  `reframe_mode` on selection, it emits a warning and leaves tracking to
  `shorts.reframe`.

### Fixed

- Added a test-isolation home so recipe cache entries never touch the
  developer's real `~/.videoflow` directory.

## [0.23.1] - 2026-10-22

### Fixed

- Recipe path parameters are now resolved through the same allowlist jail as
  media, output, and transcript paths. This covers `srt_path` and the
  overlay/music/intro/outro assets of `shorts.render` in REST and MCP runs.
- Built-in Shorts recipes now depend on the retakes step, so selection uses the
  same cull decisions as the main timeline instead of racing it.
- Operator recipes under the VideoFlow home directory override built-in recipes
  with the same id, and recipe ids are validated before any filesystem lookup.

## [0.23.0] - 2026-10-22

### Added

- **Recipe engine v1.** Recipes are versioned DAGs of typed steps with
  explicit dependencies, stable ids, parameter schemas, progress, cancellation,
  and per-step hashes. The engine validates duplicate ids, unknown step types,
  missing dependencies, disabled dependencies, and cycles before execution.
- **Step registry.** Ingest, voice detection, transcription, retakes, timeline,
  Shorts selection, Shorts rendering, and NLE export are independently
  invocable. The legacy pipeline remains available and is covered by a parity
  test against the recipe path.
- **Recipes tab, first in the workspace.** A Svelte Flow canvas edits the DAG,
  exposes JSON parameters per node, loads built-in recipes, validates, saves,
  downloads, and runs jobs with live progress.
- **Recipe API.** `GET /api/v1/steps`, `GET /api/v1/recipes`,
  `GET /api/v1/recipes/{id}`, `PUT /api/v1/recipes/{id}`,
  `POST /api/v1/recipes/validate`, and `POST /api/v1/recipes/run`.
- **Recipe MCP tools.** `videoflow_list_steps`, `videoflow_list_recipes`,
  `videoflow_get_recipe`, `videoflow_validate_recipe`,
  `videoflow_save_recipe`, `videoflow_run_recipe`, and
  `videoflow_run_recipe_inline`.
- **Recipe CLI.** `videoflow recipe list|steps|show|validate|run`.
- **Built-in recipes and examples.** `youtube_talking_head`,
  `viral_shorts_batch`, and `full_podcast_curation`, mirrored under `recipes/`.
- **LLM router.** OpenAI-compatible local/cloud endpoints are the default; an
  opt-in OpenCode CLI adapter adds timeouts, a non-shell subprocess, output
  limits, and strict JSON parsing. Secrets are stored by environment variable
  name, never inside recipes.
- **Recipe JSON Schema** at `schemas/recipe.schema.json`.

### Notes

- The visual editor is additive: the existing Speech, Edit, Shorts, Studio,
  Export, Models, Services, and Providers tabs remain available.
- The v1 recipe scope is the current pipeline. B-roll, TTS, and new vision
  models remain future steps.

## [0.22.3] - 2026-10-21

### Fixed

- Moved the workspace tabs (Speech, Edit, Shorts, Studio, Export, Models,
  Services, Providers) directly under the header as a sticky navigation bar.
  Shorts, Models, and Services no longer disappear below the New project card.
- Removed a duplicated connection banner inside the header that pushed the page
  down and made the tab bar harder to find.
- Added cache-control headers: `index.html` and `/` are `no-store`; hashed
  `_app/immutable` assets are immutable; other UI assets are revalidated.
- The browser now opens with `?v=<version>`, preventing an old UI bundle from
  being reused after an update.
- Added a UI/server version mismatch banner with a **Reload UI** action.
- Added a per-port startup lock so double-clicking the AppImage several times
  does not start competing servers; later launches wait for health and open the
  existing UI.
- Verified the AppImage starts from a detached, no-terminal session, keeps
  running, serves the UI, and exposes the Services tab.

## [0.22.2] - 2026-10-21

### Fixed

- Starting a new VideoFlow build no longer reuses an older service on the same
  port. The launcher reads `/health`, compares versions, stops the old
  VideoFlow process tree, waits for the port, and starts the current version.
  This removes the "already running" loop that kept a 0.20.0 service alive.
- Discovery now finds VideoFlow `serve`/`mcp`/`desktop` processes through
  `/proc`, including AppImage-mounted binaries and their parent processes.
- Added a **Services** tab with the current PID, port, version, URL, other
  VideoFlow services, per-process Stop, Stop all others, Restart current, and
  Stop current.
- The Services tab shows the server log and its path; startup, version
  replacement, cleanup, restart, and crashes are appended to
  `videoflow-data/logs/server.log`.
- `videoflow status` now lists discovered services in addition to the PID file.
- Cleanup stops port-owning children before launchers/parents and falls back to
  SIGKILL when SIGTERM does not finish in time.

## [0.22.1] - 2026-10-21

### Fixed

- The local file browser no longer turns a damaged or out-of-range file
  timestamp, unreadable entry, or deleted current directory into an HTTP 500.
  Failed entries are skipped and the picker offers "Open Home folder".
- Service lifecycle: `serve` keeps the executable running, writes
  `server.pid`, detects an already-running instance, and can be managed with
  `videoflow status`, `videoflow stop`, and `videoflow restart`.
- The rack header now has **Restart service** and **Stop service** buttons.
  Restart reuses the in-memory job manager and recreates the MCP session.
- The AppImage starts in the user's home directory and prints explicit
  instructions for keeping the service running or stopping it.

## [0.22.0] - 2026-10-21

### Added

- OpenAI-compatible multimodal Short analysis through
  `POST /api/v1/jobs/{job_id}/shorts/{index}/analyze/llm` and
  `videoflow_analyze_short_llm`. Frames are sampled locally, sent only when
  external services are enabled, and the result is persisted in `shorts.json`.
- A separate Studio tab with AI Analysis, Timeline, Keyframes, Tracks, and
  Transitions sections. AI Analysis runs vision analysis; Timeline opens the
  per-Short editor; the other sections expose reframe, track, and transition
  state.
- LLM emoji captions: `POST /api/v1/jobs/{job_id}/shorts/{index}/captions/emoji`
  and `videoflow_generate_short_emoji` generate a validated emoji map and
  re-render the Short with it.
- Optional model downloads through `GET /api/v1/models`,
  `POST /api/v1/models/{id}/install`, `DELETE /api/v1/models/{id}`, the Models
  tab, and three MCP tools. Downloads are checksum-verified and stored under
  the portable home directory.
- Lean portable builds: speech model weights are excluded unless
  `VIDEOWFLOW_BUNDLE_MODELS=1` or `scripts/build_portable.py --with-models` is
  used. Downloaded models are resolved at runtime without rebuilding.
- 30 transcription language codes across CLI/API/MCP/UI, including auto-detect.
- Short render resolution selection: 1080, 1440, or 2160 short-edge. 4K renders
  as 2160x3840 vertical, 2160x2160 square, or 3840x2160 landscape.

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
- Caption profanity masking with a configurable word list/replacement.
- Optional filler-word cuts for Shorts when word timings are available.
- Deterministic social metadata (title, description, hashtags, character limits)
  for YouTube, TikTok, Instagram, and LinkedIn, exposed via API/MCP and the
  Short editor's Metadata tab.
- Caption keyword highlighting, contextual emoji mapping, and brand vocabulary
  rewriting. Empty keyword lists auto-select frequent content words.
- Custom TTF/OTF font upload with internal-family detection, a local font asset
  store, UI font picker, `fontsdir` rendering, and API/MCP access.
- Short thumbnail generator: frame extraction plus caption-style title overlay,
  persisted under `shorts/thumbs/` and exposed through API/MCP/UI.
- Optional FFmpeg speech enhancement for rendered Shorts: high-pass, FFT
  denoise, and loudness normalization, with API/MCP/UI/CLI controls.
- Watermark overlay: PNG/JPEG asset store, position/margin/width/opacity
  controls, API/MCP/UI access, and post-caption compositing.
- Background music: MP3/WAV/M4A/AAC/OGG asset store, looping bed, volume,
  fades, sidechain ducking, and AAC mix output.
- External TTS voice-over: OpenAI-compatible synthesis, environment-only API
  key, original-audio ducking, mixed MP4, API/MCP/UI controls.
- Intro/outro image cards with configurable durations, normalized size, silent
  audio, and API/MCP/UI access.
- Translation dubbing: external LLM translation, TTS synthesis, dub-only mix,
  and API/MCP/UI controls.
- Reusable brand templates bundling caption style, overlay, music, and
  intro/outro settings, with save/apply/delete and server-side job application.
- Motion-tracking reframing with frame-difference focus, optional OpenCV face
  tracking fallback, and persisted crop focus.
- Project templates and versioned config export/import for non-secret run
  options.
- Audio-energy peak analysis that boosts Short candidates and exposes peak
  counts.
- FFmpeg scene-change analysis that boosts Short candidates around visual cuts
  and exposes scene counts.
- Public URL import through yt-dlp, external-policy guarded, with API/MCP/UI
  integration and normal media probing.
- Webhook publishing and scheduling with target CRUD, generated metadata, a
  durable queue, bearer-token secret references, and a local daemon.
- Optional multimodal Short analysis: audio-emotion heuristics, visual motion
  regions, and OpenCV face statistics when installed.

### Changed

- `scripts/release.py` now keeps only the three newest `releases/v*` folders.
  `--keep N` changes the retention count, and the release output lists every
  pruned folder.
- Release staging is documented as the canonical artifact store. Generated
  `build/`, `dist/`, coverage files, and caches are cleaned after each release.
- MCP now exposes thirty-six tools and four resources.

### Docs

- Refreshed the README, module specs, testing notes, UI spec, and operator
  manuals to describe FCPXML audio fades, the caption preview, the tabbed rack,
  provider policy, Short aspect ratios, and the three-release retention policy.

### Verified

- Tests: 370 passed, 11 xfailed, 7 deselected; coverage 99.06%; ruff and mypy
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
