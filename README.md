# VideoFlow

Local, non-destructive video pre-edit pipeline with a sequential rack UI and an
MCP server. VideoFlow turns a raw talking-head recording into an editable
timeline: it removes silence and retakes, adds J-cuts and punch-ins, proposes
vertical shorts, and exports timelines for DaVinci Resolve, Adobe Premiere Pro,
and Kdenlive.

> Status: 0.6.0 alpha. A portable single executable runs ingest, silence
> detection, transcript-driven retake culling, deterministic cuts, and three NLE
> exports. The local API, MCP server, and rack UI execute real jobs. Silero,
> Whisper, shorts, and NLE transitions are specified and stubbed.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- FFmpeg and FFprobe on `PATH`
- Optional: an NVIDIA GPU with CUDA for Faster-Whisper and Silero-VAD
- Optional: DaVinci Resolve, Premiere Pro, and Kdenlive 25.04+ for manual import QA

CPU is the default. No model download happens at install time.

## Quick start

```bash
uv sync --extra dev
uv run pytest                       # 202 passing, 16 strict xfail, 4 deselected
uv run pytest -q -m media --no-cov  # real FFmpeg ingest and silence detection
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
`--with-ffmpeg`:

```bash
uv run python scripts/build_portable.py --fetch-ffmpeg
./dist/videoflow doctor
./dist/videoflow demo -o ./demo
./dist/videoflow run ~/Videos/interview.mp4 -o ./interview-edit
./dist/videoflow serve              # API + MCP HTTP + rack UI
./dist/videoflow mcp                # MCP over stdio
```

Build on the target OS: PyInstaller cannot cross-compile. The CI matrix at
`.github/workflows/portable.yml` builds and smoke-tests Linux and Windows. See
[docs/manuals/portable.md](docs/manuals/portable.md).

## Implemented

- FFprobe ingest: rational frame rate, duration in frames, dimensions, sample
  rate; missing audio or unreadable files fail with a typed error.
- Mono PCM extraction and SHA-256 media fingerprint.
- Model-free speech detection through FFmpeg `silencedetect`, so the portable
  binary needs no model download.
- SRT transcript import and retake culling with exact repeats or an
  OpenAI-compatible LLM, protected by the keep-last guard.
- Deterministic timeline: frame-quantised video, sample-aligned audio, merged
  speech spans, J/L-cut audio boundaries with handle checks, logarithmic fade
  metadata, and alternating punch-ins.
- FCPXML 1.9/1.10 for Resolve, xmeml for Premiere, and OTIO for Kdenlive, from
  one validated timeline. J/L-cuts are represented with `audioStart` and
  `audioDuration` in FCPXML.
- Pure domain: rational time, cache hashing, planning, retake guard, path jail,
  redaction, schema generation.
- MCP server with twelve tools and four resources, plus a loopback health
  endpoint and Streamable HTTP mount.
- Unified CLI (`run`, `serve`, `mcp`, `doctor`, `demo`, `version`) and a
  PyInstaller onefile build for Linux and Windows.
- Local job API with SSE progress, and MCP tools that start, poll, and cancel
  real pipeline jobs.

## Not implemented yet

- Silero VAD, Faster-Whisper, and built-in transcription.
- Project-scoped REST routes beyond jobs, and transcript/shorts API tools.
- NLE audio transitions and keyframed progressive zooms.
- Face tracking, MP4 rendering, and the interactive rack.
- A signed Windows binary (SmartScreen will warn).

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
