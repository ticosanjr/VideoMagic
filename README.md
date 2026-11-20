# VideoFlow

Local, non-destructive video pre-edit pipeline controlled through MCP.
VideoFlow turns a raw talking-head recording into an editable timeline: it
removes silence and retakes, adds J-cuts and punch-ins, proposes vertical
Shorts, masters the dialogue bed, and exports timelines for DaVinci Resolve,
Adobe Premiere Pro, and Kdenlive.

> Status: 3.9.2 local stable. **35 MCP tools**, 22 styles, stateful step
> chains, multi-NLE delivery, and opt-in Windows GPU offload with a
> self-healing worker kit. GPU speed certification awaits Windows/NVIDIA
> hardware. The local Linux binary and AppImage run ingest, Silero VAD with an
> FFmpeg fallback, local Faster-Whisper quality transcription with a
> whisper.cpp fallback, SRT/ASR paths, transcript-driven retake culling,
> deterministic cuts, vertical Shorts, audio mastering and loudness QA, burned
> titles, color/LUT grading, review approval, thumbnail A/B, translation, and
> three NLE exports. The local UI is limited to MCP configuration and
> observability: jobs, models, providers, services, extensions, connections,
> GPU, and settings. Projects persist atomic, revisioned JSON state under
> `.videoflow/`; SQLite indexes jobs and assets; settings, providers, secrets,
> models, plugins, and diagnostics are configurable locally.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- FFmpeg and FFprobe on `PATH`
- Optional: DaVinci Resolve, Premiere Pro, and Kdenlive 25.04+ for manual import QA

CPU is the default. The lean portable release bundles whisper.cpp and
Faster-Whisper runtimes but not their large weights; download the small model
from the Models tab when needed. A build with `--with-models` embeds the weights
and works fully offline out of the box. A GPU is not required.

## MCP usage

Create a project, discover nodes with `vf_catalog_search` or
`vf://docs/steps`, run them with `vf_exec(action="step")`, then inspect the
job and export the delivery bundle:

```text
vf_project(action="init", output="/projects/interview", sources=["/media/a.mp4"])
vf_exec(action="step", step_id="ingest", params={"sources": ["/media/a.mp4"]})
vf_exec(action="step", step_id="transcribe", params={"language": "pt"})
vf_exec(action="step", step_id="edit.timeline", params={})
vf_export(project_id="...", targets="all")
```

The local UI only configures models, providers, services, plugins, MCP
connections, the GPU worker, and runtime settings. See [docs/mcp.md](docs/mcp.md).

## Quick start

```bash
uv sync --extra dev --extra faster-whisper
uv run pytest                       # 1,723 passing, 1 strict xfail, 18 deselected
uv run pytest -q -m media --no-cov  # real FFmpeg ingest and silence detection
uv run python scripts/fetch_whisper.py         # optional GGML model into vendor/
uv run python scripts/fetch_silero.py          # pinned 2.3 MB VAD model
uv run python scripts/fetch_faster_whisper.py  # pinned 484 MB Faster-Whisper model
uv run videoflow-api                # http://127.0.0.1:8765/health and /mcp
uv run videoflow-mcp                # stdio transport for a local agent
```

The recipe studio UI lives in `ui/`:

```bash
cd ui
npm install
npm run dev                         # http://127.0.0.1:5173
```

## Local release build

The official release is built and staged locally. The GitHub Actions
workflows are manual fallbacks for CI, Windows, and release assets; nothing
runs on push.

```bash
./scripts/gate_local.sh              # fast: ruff, changed tests, UI unit
./scripts/gate_local.sh --full       # full: media, coverage, E2E, perf
./scripts/release_fast.sh 2.0.0      # onedir bundle + tar.zst
./scripts/release_local.sh 2.0.0     # onefile + AppImage + SBOM
```

`release_fast.sh` is the iteration path: it bumps the version, runs the fast
gate, reuses the PyInstaller cache, and stages
`VideoFlow-X.Y.Z-linux-x86_64.tar.zst`. Extract it with
`tar --zstd -xf ...` and run `./videoflow/videoflow doctor`.

`release_local.sh` is the complete path: full gate, UI, onefile binary,
AppImage, SBOM, and checksums. Both write `releases/vX.Y.Z/SHA256SUMS` and
`manifest.json`; nothing is pushed or published. The three newest release
folders are kept.


## Portable executable

One file per OS, no Python, Node, or FFmpeg install required when built with
`--fetch-ffmpeg --with-whisper --with-silero --with-faster-whisper`. Models are
not embedded by default; add `--with-models` for a fully offline artifact.

```bash
uv run python scripts/build_portable.py --fetch-ffmpeg --with-whisper \
  --with-silero --with-faster-whisper --with-tray
./dist/videoflow doctor
./dist/videoflow recipe run youtube_talking_head ~/Videos/interview.mp4 -o ./interview-edit
./dist/videoflow serve --open       # API + MCP HTTP + studio UI, stays running
./dist/videoflow tray               # tray icon that owns the local service
./dist/videoflow status             # PID, URL, and all discovered services
./dist/videoflow restart            # stop, then start again
./dist/videoflow stop               # stop the local service
./dist/videoflow mcp                # MCP over stdio
```

`videoflow tray` needs the optional tray extra in a source checkout
(`uv sync --extra tray`) and a desktop session. Release builds include
`pystray`, Pillow, and `python-xlib` via `--with-tray`. The tray owns the local
service. Use `videoflow tray --check` to print the backend, display, and whether
the menu is available.
Clicking the icon opens a menu with the version, service/job status, **Open
VideoFlow**, **Open runs**, **Restart service**, start/stop, job controls, and
**Quit VideoFlow** (which stops the service and exits). On Linux the full menu
needs PyGObject and Ayatana AppIndicator:

```bash
sudo apt install python3-gi gir1.2-ayatanaappindicator3-0.1
```

Without them the tray falls back to the xorg backend: the icon appears, but that
backend can only run a default action and has no menu. Because the menu is
required for restart/quit, `videoflow tray` falls back to `videoflow serve`
when no menu-capable backend is available. Force a backend with
`VIDEOWFLOW_TRAY_BACKEND=appindicator|gtk|xorg`.

The local release is the canonical artifact build:

```bash
uv run python scripts/build_portable.py --fetch-ffmpeg --with-whisper \
  --with-silero --with-faster-whisper                    # Linux
uv run python scripts/build_appimage.py                  # VideoFlow-X.Y.Z-x86_64.AppImage
./scripts/release_fast.sh 2.0.0                          # fast onedir + tar.zst
./scripts/release_local.sh 2.0.0                         # onefile + AppImage + SBOM + checksums
```

Build caches in `build/`, `dist/`, `vendor/`, `ui/node_modules`, and `build/videoflow-base` are intentionally preserved so the next build is incremental. Nothing deletes them automatically. Use `./scripts/release_local.sh --clean 2.0.0` or `./scripts/release_fast.sh --clean 2.0.0` only after changing dependencies or the PyInstaller spec. `--refresh-runtime` rebuilds the fast runtime without discarding the rest of the cache.

See [docs/manuals/portable.md](docs/manuals/portable.md).

## Implemented

- FFprobe ingest: rational frame rate, duration in frames, dimensions, sample
  rate; missing audio or unreadable files fail with a typed error.
- Mono PCM extraction and SHA-256 media fingerprint.
- Professional shell: command palette (`Ctrl/Cmd+K`), shortcut reference,
  activity drawer, notification center, and g-prefixed tab jumps.
- Job dashboard with status buckets, search, progress, next-action guidance,
  guarded cancel, and retry.
- Real cancellation: FFmpeg runs in its own process group and is terminated on
  cancel or timeout, with partial output removed.
- Timeline pro editing: real per-clip waveforms, group trim, slip, ripple trim,
  viewport virtualization, and a debounced preview scheduler. Locked tracks
  reject edits; muted audio renders silent.
- Content quality: a golden set with six channel profiles (calibrated
  precision@1 1.00 vs 0.75 baseline), shot-aware B-roll with a licence report,
  an SFX library, a delivery package that applies the winning thumbnail, and
  the `localized_shorts` recipe with dubbing after the render.
- Native NLE finishing: titles, markers, chapters, colour filters, a B-roll
  lane, and the audio master in FCPXML, XMEML, and Kdenlive, plus
  `scripts/qa_nle.py` to fail an export that loses them.
- Human-in-the-loop: durable approvals, questions, file handoffs, local/e-mail/
  Slack/Signal notifications, and the favorited `full_ai_editor` recipe with
  research, dual script, decoupage, asset license, motion, audio, fact-check,
  voice-repair, and final approval checkpoints.
- Research and assets: local/SearXNG/Wikipedia/Internet Archive research,
  citation manifests, Pexels/Pixabay/Openverse/Wikimedia harvesting, short
  fair-use YouTube excerpts, an explicit license ledger, and export gating.
- Motion and audio: JSON scene codegen, FFmpeg motion rendering, procedural
  copyright-free music/Foley, final dialogue/music/SFX mix, and intro compiler.
- Professional finishing: pause/resume and priority, slide, duplicate, per-clip
  comments, context menu, drag-and-drop timeline overlays, incremental Shorts
  and segment-cached timeline renders, frame preview, light/high-contrast
  themes, compact density, crash reports, and token metrics.
- Copilot: LLM-backed recipe drafts and timeline edit plans through a
  configured provider or managed local service, with domain validation before
  anything is written.
- Integrations: MCP (stdio and HTTP) plus REST for OpenCode and Paperclip,
  with DeepSeek provider/service setup and copy-ready prompts.
- Intuitive shell: five workflow areas, legacy route aliases, searchable
  settings, HelpTip/FieldHint, status legends, empty states, and copy standards.
- Silero VAD v5.1.2 through ONNX Runtime, with 16 kHz inference, exact
  sample-rate rescaling, configurable threshold, and pads. FFmpeg
  `silencedetect` is the automatic fallback.
- SRT transcript import and retake culling with exact repeats or an
  OpenAI-compatible LLM, protected by the keep-last guard.
- Offline Faster-Whisper 1.2.1/CTranslate2 quality transcription with word
  timestamps, a pinned small model, full-WAV decoding, and exact floor/ceil
  sample conversion. whisper.cpp and `ggml-tiny.bin` remain the automatic
  fallback; larger CTranslate2 and GGML models can be selected locally.
- Optional ASR HTTP through an OpenAI-compatible `/audio/transcriptions`
  endpoint.
- Vertical/social shorts: deterministic or LLM selection, prompt/reprompt
  focus, explainable virality scoring, auto-hook metadata/repeat/reorder,
  optional filler-word cuts, profanity-masked captions, keyword/emoji/brand
  caption styling, custom font upload, optional speech enhancement, watermark
  overlays, intro/outro cards, music beds with ducking, external TTS voice-over,
  translation dubbing, brand templates, project templates/config import-export,
  motion/face-assisted reframing, audio-energy and scene-change curation,
  platform metadata, URL import, webhook publishing/scheduling,
  OpenAI-compatible multimodal vision analysis, LLM emoji captions, thumbnails,
  retake-aware conforming, 9:16/4:5/3:4/2:3/1:1/16:9 render at 1080/1440/2160 short edge,
  30 fps social masters with optional NVENC, fast export QA, and full QA in the background,
  an optional source window, burned ASS captions, a live aspect-aware preview,
  and a per-Short trim/retitle/reframe editor.
- Deterministic timeline: frame-quantised video, sample-aligned audio, merged
  speech spans, J/L-cut audio boundaries with handle checks, logarithmic fade
  metadata, and alternating punch-ins.
- FCPXML 1.9/1.10 for Resolve, xmeml v4 for Premiere, and native `.kdenlive`
  MLT XML for Kdenlive, from one validated timeline. J/L-cuts are represented
  with `audioStart` and `audioDuration` in FCPXML. All three artifacts carry
  audio fades, and the FCPXML output validates against Apple's 1.9 DTD.
- Pure domain: rational time, cache hashing, planning, retake guard, path jail,
  redaction, schema generation.
- MCP server with seventeen core tools and thirteen resources: project setup,
  node catalog, step execution, jobs, timeline edits, artifacts, render, NLE
  export, and project state/preset/export resources. The `opencode` profile is
  the default; recipes and generic prompts are not exposed. OpenCode direction
  lives in AGENTS.md, workflows, and the 18-style catalog.
  Streamable HTTP is mounted on the local API.
- Unified CLI (`version`, `doctor`, `shorts`, `recipe`, `serve`, `status`,
  `restart`, `stop`, `mcp`) and a PyInstaller onefile build for Linux and
  Windows.
- Recipes-first workspace: a Svelte Flow DAG editor backed by a typed recipe
  engine, plus the classic Speech, Edit, Shorts, Studio, Export, Models,
  Services, and Providers tabs, a capability manifest, opt-in external-provider policy, a model downloader,
  Short aspect/window/resolution controls, a Services tab for process cleanup,
  and Restart/Stop service buttons.
- Local job API with SSE progress, plus persistent project routes for media,
  module config, provider policy, transcript overrides, exports, and operator
  presets.
- MCP tools that start, poll, and cancel real pipeline jobs.
- Direct main-timeline MP4 render from the validated timeline.
- Progressive zoom keyframes in FCPXML, XMEML, and MP4.
- Crossfade and fade-to-black transitions in FCPXML, XMEML, and MP4.
- Folder batches with one job per file, item-level progress, cancellation, and checkpoints.
- Run comparison: previous versus current step status, timings, cache hits, and warnings.
- Persistent run history in `work/run-history.json`, readable through `GET /api/v1/runs`.
- Local release script for Linux/AppImage; Windows cross-build is optional and separate.
- Optional `--onedir` PyInstaller build.
- Heuristic speaker turns with speaker-colored ASS captions.
- Local B-roll planning and full-frame B-roll overlays for Shorts.
- Split-screen Shorts rendering.
- Local Piper TTS voice-over through the API and UI.
- Recipe inspector controls for transitions, speaker turns, B-roll, split-screen, and caption colors.
- Persisted run history browser in the recipe UI.
- Kdenlive affine transforms/keyframes plus opacity/volume transition filters.
- Optional pyannote model-based diarization with heuristic fallback.
- Pexels stock B-roll provider alongside local assets.
- Automatic split-screen for multi-speaker dialogue clips.
- Failed recipe runs persist a `work/failure.json` with the failing stage, error, FFmpeg command, stderr, and log tail.
- Playwright E2E tests for the recipe graph, inspector, schema fields, palette, NLE validation, and run-history browser.
- Schema-derived inspector fields for primitive step parameters.
- NLE validation from the Recipes tab.
- B-roll plan display with provider, license, and path.
- Batch history persisted as JSON and reloaded after restart.
- Two-source split-screen: left panel from the main source, right panel from a second angle.
- Repository policy test enforcing JSON for project data and tests.
- Automatic tag release workflow for Linux, AppImage, Windows, SBOM, and checksums.
- Windows smoke test (`version`, `doctor`) in CI.
- CI media tests and automatic post-run checkpoint pruning.
- Job history persisted as JSON; interrupted jobs are marked failed after restart.
- Batch resume from the API and the batch modal.
- Inline video preview for MP4 artifacts and rendered Shorts.
- MLT/Kdenlive render smoke through `scripts/melt_check.py` and a media test.
- Inline node configuration with schema-derived fields, validation, enums, path pickers, pin/expand, and saved canvas layout.
- Live per-step progress on each node.
- Two-source split-screen can mix both audio tracks.
- Stable Pexels B-roll cache keyed by source URL.
- On-demand 540p preview proxy endpoint.
- Global analysis-cache pruning by age and size.
- Legacy runner execution scaffold removed; recipe engine owns execution.
- pyannote 3.1 model downloader in the Models catalog using Hugging Face.
- Saved viewport, node width cycling, proxy preview in the UI, and persisted batch history.
- Pagination for jobs, batches, and run history.
- Canvas cycle prevention, undo/redo, array JSON fields, and UI-version build guard.
- pyannote uses an installed local model automatically; Pexels downloads stream to disk; melt reports plugin warnings.
- Per-step log viewer directly from recipe nodes.
- Recipes-first UI: legacy Speech/Edit/Shorts/Studio/Export tabs removed from navigation.
- Content-cycle nodes with available/partial/planned status, icons, colors, and automatic bypass for planned nodes.
- Local asset library and read-only storyboard/timeline tabs.
- Models grouped by capability with used-by/license/source; downloads decoupled from provider policy.
- Services doctor, destructive confirmations, and a compact provider/capability page.
- Legacy New project/ProjectTemplateManager removed; provider connection test with secret presence.
- Recipe history, save-as/duplicate, and planned conditional/loop/subflow nodes.
- Timeline caption editing and implemented storyboard/thumbnail content nodes.
- Recipe template gallery with search, save-as, history, and final 0.57 polish.
- Timeline trim/move/delete with project-state revisioning; provider connection test; services doctor; content-cycle statuses.
- Batch history list and proxy generation in the editor.
- Configuration and test data are JSON; the only YAML files are the manual GitHub workflow definitions.
- Versioned JSON migration gates for recipes and project state.
- Output maintenance: checkpoint/B-roll/run-history pruning via CLI or API.

## Not implemented yet

- Kdenlive exact cross-dissolve validation; transitions are emitted as affine opacity/volume fades.
- Pyannote is optional and requires a model/install; heuristic remains the default.
- Face tracking for the main timeline.
- Manual import validation in Resolve, Premiere, and Kdenlive (automated XML
  validation is implemented; see `docs/nle-qa.md`).
- A signed Windows binary (SmartScreen will warn), although the unsigned PE is
  built by the manual Windows workflow and attached to releases.

Known gaps are listed here; AC-01 is the only strict xfail. The others are
product decisions or external dependencies, not silently skipped contracts.

## Documentation

Start at [docs/README.md](docs/README.md).

- [Product requirements](docs/prd.md)
- [Architecture](docs/architecture.md)
- [Exporters](docs/exporters.md)
- [Data model](docs/data-model.md)
- [Test plan and coverage gates](docs/testing.md)
- [User manual](docs/manuals/user.md)
- [Operator manual](docs/manuals/operator.md)
- [MCP agent manual](docs/manuals/mcp-agent.md)

## Layout

```text
src/videoflow/      domain, application, modules, adapters, api, mcp_server, exporters
schemas/            committed JSON Schemas generated from the Pydantic models
docs/               PRD, design, module specs, ADRs, manuals
tests/unit/         passing tests for the pure core
tests/contract/     public contracts; xfail until implemented
ui/                 SvelteKit + Tailwind recipe studio and timeline
```
