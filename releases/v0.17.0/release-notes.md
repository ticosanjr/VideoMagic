# VideoFlow 0.17.0

Persistent, revisioned projects and operator presets on the local REST API.

## Highlights

- Projects live under `<root>/.videoflow/` with an atomic
  `project_state.json`, an append-only `revisions/` history, `work/`, and
  `exports/`.
- Every accepted write increments `revision` and writes the matching snapshot
  before replacing canonical state.
- REST routes create and list projects, register media, edit module config and
  enabled flags, run the full project pipeline, cancel jobs, stream SSE events,
  read transcripts, replace sentence overrides, export timelines, and apply
  presets.
- Project runs preserve `project_id`, module config, enabled flags, transcript
  word timings, manual overrides, export target flags, FCPXML dialect, and the
  next state revision.
- Operator presets under `$VIDEOWFLOW_HOME/presets/` keep partial JSON, shadow
  shipped presets by name, and apply atomically to projects.
- Shared SRT formatting now serves both the REST transcript route and MCP
  resources.
- Media registration and override writes invalidate stale derived results
  instead of leaving old timeline data looking current.

## Artifacts

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `videoflow-0.17.0-linux-x86_64` | 239.8 MB | `968bac5eed3a572c935f91083f95aff162af21cce1e384fd3bb9cc88ed93dc77` |
| `VideoFlow-0.17.0-x86_64.AppImage` | 240.0 MB | `5b92818cf67b21dde44fc9eccd5d1e82abe2347e882a1404a63e5eea14e1fb2e` |
| `videoflow-0.17.0-windows-x86_64.exe` | 224.0 MB | `391db9b7872ac2c450a9417bb44af2166da9495d90ffbf49efdda25e3d91a9bb` |

## Run

Linux plain binary:

```bash
./videoflow-0.17.0-linux-x86_64 version
./videoflow-0.17.0-linux-x86_64 doctor
./videoflow-0.17.0-linux-x86_64 demo -o demo
./videoflow-0.17.0-linux-x86_64 run input.mp4 -o project
./videoflow-0.17.0-linux-x86_64 serve
```

Linux AppImage:

```bash
chmod +x VideoFlow-0.17.0-x86_64.AppImage
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.17.0-x86_64.AppImage version
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.17.0-x86_64.AppImage demo -o demo
```

Windows:

```powershell
.\videoflow-0.17.0-windows-x86_64.exe version
.\videoflow-0.17.0-windows-x86_64.exe doctor
.\videoflow-0.17.0-windows-x86_64.exe demo -o demo
```

Project API example:

```bash
curl -s -X POST http://127.0.0.1:8765/api/v1/projects \
  -H 'Content-Type: application/json' \
  -d '{"root":"/home/editor/projects/interview"}'
```

## Verification

- Linux binary and AppImage report 0.17.0; `doctor` finds bundled FFmpeg,
  whisper, model, UI, and MCP; `demo` writes all three NLE exports.
- The AppImage smoke also exercised `--appimage-extract-and-run` and a real
  `serve` process answering `/health`.
- Frozen Linux project API flow: wrote an operator preset, created a project,
  registered media, applied the preset, ran the full pipeline, exported
  FCPXML 1.10, verified the media path jail, and confirmed revisions
  `000001.json` through `000004.json`.
- Frozen Linux MCP: twelve tools, local whisper.cpp transcription, transcript
  read, cull, pipeline success, export, and live state/exports/presets
  resources.
- Windows PE under Wine reports 0.17.0; `doctor` and `demo` pass, and the same
  frozen project API/preset flow succeeded with four revision snapshots and a
  full pipeline export.
- Tests: 269 passed, 13 xfailed, 7 deselected; coverage 99.26%; ruff and mypy
  clean.

## Caveats

- Per-module reruns return typed `501 not_implemented`; run the full project
  pipeline. Cache-backed per-block runs are the next engine pass.
- Word-level retake overrides return `word_overrides_not_supported`;
  sentence-level culling is authoritative.
- The Windows PE was built and validated under Wine, not on a native Windows
  host. Run a native smoke test before wide distribution.
- The binary is unsigned. SmartScreen will warn until a certificate is
  configured.
- LLM retake endpoints remain environment-selected through
  `VIDEOWFLOW_LLM_BASE_URL`, matching the jobs API.
- Artifacts are local. No GitHub release asset upload was performed.

See `CHANGELOG.md` for the full change list.
