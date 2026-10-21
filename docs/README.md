# VideoFlow documentation

Everything here is English. The original Portuguese brief is archived and
non-normative at [origin/prd-pt.md](origin/prd-pt.md).

## Implementation status (0.21.2)

| Area | State |
| --- | --- |
| Rational time, state, cache, planning, retake guard, path jail | implemented |
| FFmpeg ingest and PCM fingerprint | implemented |
| Silero VAD via ONNX Runtime with FFmpeg `silencedetect` fallback | implemented |
| Deterministic timeline, J/L-cuts, fades, punch-ins | implemented |
| FCPXML 1.9/1.10, xmeml v4, native Kdenlive MLT export | implemented |
| Portable artifacts | 0.21.2 Linux binary, Linux AppImage, and Windows PE built and smoke-tested under Wine; the file browser is included |
| SRT transcript import and LLM retake culling | implemented |
| Local Faster-Whisper with whisper.cpp fallback, and ASR HTTP | implemented; pinned small model bundled in release builds |
| Local filesystem browser with allowlisted roots | implemented; no media upload |
| Jobs, job REST routes, SSE, live MCP jobs | implemented for the portable path |
| MCP: twelve tools and four resources | implemented; analysis, staged edits, jobs, export, resources |
| Rack UI driving real portable jobs, logs, overrides, shorts | implemented; source/output/transcript/model selection uses the path picker |
| Project-scoped routes, revisions, transcript API, presets | implemented; per-module rerun is typed 501 |
| Shorts selection/rendering and API download | implemented |
| NLE audio fades | implemented in FCPXML, xmeml, and Kdenlive |
| Keyframed progressive zooms, direct MP4 | specified, stubbed |

Every stub has a strict `xfail` contract in `tests/contract/`.

## Start here

| Document | Read it when |
| --- | --- |
| [PRD](prd.md) | You need the normative requirements and acceptance criteria |
| [Architecture](architecture.md) | You need the boundaries, flow, and package map |
| [Data model](data-model.md) | You are changing state, presets, or schemas |
| [Timebase](timebase.md) | You are touching frames, samples, pads, or exports |
| [Pipeline](pipeline.md) | You are implementing or debugging a run |
| [Cache](cache.md) | A rerun is slower than it should be |
| [Testing](testing.md) | You are adding tests or running a release gate |
| [API](api.md) | You are wiring the UI or a script |
| [MCP](mcp.md) | You are connecting an agent |
| [UI specification](ui-spec.md) | You are building the rack |
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
