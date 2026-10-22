# VideoFlow

Local, non-destructive video pre-edit pipeline with a sequential rack UI and an
MCP server. VideoFlow turns a raw talking-head recording into an editable
timeline: it removes silence and retakes, adds J-cuts and punch-ins, proposes
vertical shorts, and exports timelines for DaVinci Resolve, Adobe Premiere Pro,
and Kdenlive. The primary surface is a recipe DAG editor; the classic rack
panels remain available for manual control.

> Status: 0.38.0 alpha. The portable Linux binary, Linux AppImage, and Windows
> PE run ingest, Silero VAD with an FFmpeg fallback, local Faster-Whisper
> quality transcription with a whisper.cpp fallback, SRT/ASR paths,
> transcript-driven retake culling, deterministic cuts, vertical shorts, and
> three NLE exports. The local API, MCP server, and rack UI execute real jobs;
> all fifty-two MCP tools and four resources are live, including recipe, step, and folder-batch execution. The rack browses local files
> and folders instead of requiring typed paths. Projects persist atomic,
> revisioned state under `.videoflow/`, and the REST API manages media, modules,
> transcripts, exports, and operator presets.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- FFmpeg and FFprobe on `PATH`
- Optional: DaVinci Resolve, Premiere Pro, and Kdenlive 25.04+ for manual import QA

CPU is the default. The lean portable release bundles whisper.cpp and
Faster-Whisper runtimes but not their large weights; download the small model
from the Models tab when needed. A build with `--with-models` embeds the weights
and works fully offline out of the box. A GPU is not required.

## Recipes

A recipe is a JSON DAG shared by the UI, CLI, REST API, and MCP tools:

```bash
videoflow recipe list
videoflow recipe validate recipes/youtube_talking_head.json
videoflow recipe run recipes/viral_shorts_batch.json /media/source.mp4 -o /media/out
```

The same contract is available at `POST /api/v1/recipes/run` and through
`videoflow_run_recipe_inline`. See `docs/recipes.md` and
`schemas/recipe.schema.json`.

## Quick start

```bash
uv sync --extra dev --extra faster-whisper
uv run pytest                       # 439 passing, 10 strict xfail, 8 deselected
uv run pytest -q -m media --no-cov  # real FFmpeg ingest and silence detection
uv run python scripts/fetch_whisper.py         # optional GGML model into vendor/
uv run python scripts/fetch_silero.py          # pinned 2.3 MB VAD model
uv run python scripts/fetch_faster_whisper.py  # pinned 484 MB Faster-Whisper model
uv run videoflow-api                # http://127.0.0.1:8765/health and /mcp
uv run videoflow-mcp                # stdio transport for a local agent
```

The rack UI scaffold lives in `ui/`:

```bash
cd ui
npm install
npm run dev                         # http://127.0.0.1:5173
```

## Portable executable

One file per OS, no Python, Node, or FFmpeg install required when built with
`--fetch-ffmpeg --with-whisper --with-silero --with-faster-whisper`. Models are
not embedded by default; add `--with-models` for a fully offline artifact.

```bash
uv run python scripts/build_portable.py --fetch-ffmpeg --with-whisper \
  --with-silero --with-faster-whisper
./dist/videoflow doctor
./dist/videoflow demo -o ./demo
./dist/videoflow run ~/Videos/interview.mp4 -o ./interview-edit --transcribe
./dist/videoflow serve --open       # API + MCP HTTP + rack UI, stays running
./dist/videoflow status             # PID, URL, and all discovered services
./dist/videoflow restart            # stop, then start again
./dist/videoflow stop               # stop the local service
./dist/videoflow mcp                # MCP over stdio
```

Artifacts are built locally, never in GitHub Actions:

```bash
uv run python scripts/build_portable.py --fetch-ffmpeg --with-whisper \
  --with-silero --with-faster-whisper                    # Linux
uv run python scripts/build_appimage.py                  # VideoFlow-X.Y.Z-x86_64.AppImage
# Windows PE: Windows Python + PyInstaller, or Wine + embeddable Python
uv run python scripts/release.py --require-all             # stage and keep 3 releases
rm -rf build dist .coverage .hypothesis .pytest_cache .mypy_cache .ruff_cache
```

See [docs/manuals/portable.md](docs/manuals/portable.md).

## Implemented

- FFprobe ingest: rational frame rate, duration in frames, dimensions, sample
  rate; missing audio or unreadable files fail with a typed error.
- Mono PCM extraction and SHA-256 media fingerprint.
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
  retake-aware conforming, 9:16/1:1/16:9 render at 1080/1440/2160 short edge,
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
- MCP server with forty-one live tools and four resources: media ingest,
  capability discovery, Silero speech detection, local
  Faster-Whisper/whisper.cpp transcription, transcript reads, staged
  retake/zoom/J-cut edits, shorts proposals, real jobs, NLE export, and project
  state/preset/export resources. Streamable HTTP is mounted on the local API.
- Unified CLI (`run`, `serve`, `mcp`, `doctor`, `demo`, `version`) and a
  PyInstaller onefile build for Linux and Windows.
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
- GitHub Actions for Linux tests and a Windows portable build.
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
- Configuration and test data are JSON; the only YAML files are the GitHub Actions workflows, which GitHub requires.
- Versioned JSON migration gates for recipes and project state.
- Output maintenance: checkpoint/B-roll/run-history pruning via CLI or API.

## Not implemented yet

- Legacy project-scoped module reruns now start the full project pipeline (or
  return a cached no-op); recipe steps remain the checkpointed path.
- Kdenlive exact cross-dissolve validation; transitions are emitted as affine opacity/volume fades.
- Pyannote is optional and requires a model/install; heuristic remains the default.
- Face tracking for the main timeline.
- Manual import validation in Resolve, Premiere, and Kdenlive (automated XML
  validation is implemented; see `docs/nle-qa.md`).
- A signed Windows binary (SmartScreen will warn), although the unsigned PE is
  built by CI and attached to releases.

Every unimplemented contract has a test marked `xfail`, so the suite stays green
while the specification stays executable.

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
ui/                 SvelteKit + Tailwind rack scaffold
```
