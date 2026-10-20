# VideoFlow 0.18.0

Silero VAD becomes the quality speech detector, with FFmpeg `silencedetect` as
the automatic offline fallback.

## Highlights

- Silero VAD v5.1.2 runs through ONNX Runtime on the CPU: 16 kHz mono PCM,
  512-sample windows, a carried `state` tensor, a configurable probability
  threshold, gap merging, and minimum-speech filtering.
- `vad_engine` is typed as `auto`, `silero`, or `ffmpeg`. `auto` prefers Silero
  only when the pinned model and ONNX Runtime are available. An explicit
  `silero` request fails with an actionable model/runtime hint instead of
  silently downgrading.
- 16 kHz windows are mapped back to source-rate sample spans with exact integer
  floor/ceil arithmetic. Speech pads are applied after retake culling, so a
  culled take cannot survive as pad-only audio.
- The CLI, job API, project config, MCP `videoflow_run_vad`, and rack UI expose
  the engine, threshold, and pads. Job results and `run.json` report
  `vad_engine`; `doctor` reports the model and ONNX Runtime.
- `scripts/fetch_silero.py` pins the v5.1.2 URL and verifies SHA-256
  `2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f`.
  `build_portable.py --with-silero` bundles the 2.3 MB model and ONNX Runtime.
- `videoflow demo` uses FFmpeg explicitly, so the self-contained demo does not
  depend on the optional VAD model.

## Artifacts

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `videoflow-0.18.0-linux-x86_64` | 281.4 MB | `828d158164dccc81b6ca140a7c8355ae0d145b189d45cf0116931ba46639622f` |
| `VideoFlow-0.18.0-x86_64.AppImage` | 281.4 MB | `79bf39e1121d6ac6ca18f9ee6343512a8ded6c6233a0fd8aaac1f21bef89f912` |
| `videoflow-0.18.0-windows-x86_64.exe` | 252.7 MB | `79d80daf1a985829240a3d25b179dbbf24365a78483636816ea3dd3e87a429f3` |

The binaries stay beside these notes locally and are ignored by git. They were
not uploaded to GitHub.

## Run

Linux plain binary:

```bash
./videoflow-0.18.0-linux-x86_64 version
./videoflow-0.18.0-linux-x86_64 doctor
./videoflow-0.18.0-linux-x86_64 demo -o demo
./videoflow-0.18.0-linux-x86_64 run input.mp4 -o project --vad-engine auto
./videoflow-0.18.0-linux-x86_64 serve
```

Linux AppImage:

```bash
chmod +x VideoFlow-0.18.0-x86_64.AppImage
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.18.0-x86_64.AppImage version
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.18.0-x86_64.AppImage demo -o demo
```

Windows:

```powershell
.\videoflow-0.18.0-windows-x86_64.exe version
.\videoflow-0.18.0-windows-x86_64.exe doctor
.\videoflow-0.18.0-windows-x86_64.exe demo -o demo
.\videoflow-0.18.0-windows-x86_64.exe run input.mp4 -o project
```

Use `--vad-engine silero` to require the quality path or `--vad-engine ffmpeg`
to force the fallback.

## Verification

- Linux binary: `version` and `doctor` pass with bundled FFmpeg, whisper, UI,
  MCP, the Silero model, and ONNX Runtime 1.31.0. A real `jfk.mp4` run reported
  `"vad_engine": "silero"` with 3 speech intervals.
- AppImage smoke exercised `version`, `doctor`, `demo`, extract-and-run, and a
  real `serve` process answering `/health`.
- Frozen Linux project API flow created a project, registered media, ran the
  full pipeline with Silero, exported FCPXML 1.10, and wrote revisions
  `000001.json` through `000004.json`.
- Frozen Linux MCP flow passed with twelve tools and four resources: load, VAD
  (`vad_engine=silero`), local whisper.cpp transcription, transcript read,
  cull, pipeline job (`vad_engine=silero`), export, state, and presets.
- Missing-model fallback was verified: `auto` reported `vad_engine=ffmpeg`;
  explicit `silero` exited 1 with `ingest_failed` and the model fetch/build hint.
- Windows PE under Wine: `version`, `doctor` (Silero and ONNX Runtime found),
  a real Silero run (3 intervals), `demo`, the project API flow, and the MCP
  flow all pass with `vad_engine=silero`.
- Tests: 284 passed, 12 xfailed, 7 deselected; coverage 99.26%; ruff and mypy
  clean; UI `check`, 8 Vitest tests, and the production build pass.

## Caveats

- The Windows PE was built and validated under Wine, not on a native Windows
  host. Run a native smoke test before wide distribution.
- Silero inference is CPU-only in 0.18. `auto` degrades to FFmpeg when the
  model or ONNX Runtime is absent; explicit `silero` does not.
- Per-module reruns still return typed `501 not_implemented`; run the full
  project pipeline. Faster-Whisper quality transcription remains the next
  engine pass.
- Word-level retake overrides return `word_overrides_not_supported`;
  sentence-level culling is authoritative.
- The binary is unsigned. SmartScreen will warn until a certificate is
  configured.

See `CHANGELOG.md` for the full change list.
