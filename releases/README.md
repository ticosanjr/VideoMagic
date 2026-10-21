# Releases

Every release gets a versioned folder:

```
releases/v0.4.0/
  videoflow-0.4.0-linux-x86_64    # local artifact, ignored by git
  SHA256SUMS                      # tracked
  manifest.json                   # tracked
  release-notes.md                # tracked
```

## Policy

1. Stage the artifacts with `uv run python scripts/release.py --version X.Y.Z`.
2. Verify `version`, `doctor`, `demo`, and the three exports on each artifact.
3. Commit the notes, checksums, and manifest. Binaries are ignored because
   GitHub rejects files over 100 MB in normal git history.
4. Keep the binaries in this folder. GitHub Actions is not used for this
   project. Uploading to a GitHub Release is a separate, manual decision.

```bash
uv run python scripts/build_portable.py --fetch-ffmpeg --with-whisper \
  --with-silero --with-faster-whisper
uv run python scripts/build_appimage.py
# Windows PE via Wine + embeddable Python, see docs/manuals/portable.md
uv run python scripts/release.py
```

A release is not complete until the Linux binary, AppImage, and Windows `.exe`
exist in the version folder and their checksums are recorded here. Every asset
name includes the version, for example:

```
videoflow-0.9.0-linux-x86_64
VideoFlow-0.9.0-x86_64.AppImage
videoflow-0.9.0-windows-x86_64.exe
```

## Current

- `v0.21.1`: Premiere xmeml audio `transitionitem` fades and Kdenlive keyframed
  `volume` fades. Linux binary, AppImage, and Windows PE built and smoke-tested.
- `v0.21.0`: configurable zoom bounds, audio fades, Shorts target/minimum and
  selection strategy, `run --shorts`, and full caption/karaoke styling across
  UI, API, project config, presets, and MCP. Linux binary, AppImage, and Windows
  PE built and smoke-tested.
- `v0.20.1`: Resolve FCPXML media-rep, Premiere xmeml v4 full-file/link fix,
  and native Kdenlive `.kdenlive` MLT export. Linux binary, Linux AppImage, and
  Windows PE built and smoke-tested.
- `v0.20.0`: local filesystem browser for source/output/SRT/model selection,
  source metadata preview, folder creation, and a modernized rack setup. Linux
  binary, Linux AppImage, and Windows PE built and smoke-tested.
- `v0.19.0`: local Faster-Whisper 1.2.1 with the pinned small CTranslate2
  model, full-WAV word timestamps, whisper.cpp fallback, and bundled runtime.
- `v0.18.0`: Silero VAD v5.1.2 via ONNX Runtime, engine selection and fallback,
  source-rate pads, and bundled model/runtime in the portable builds.
- `v0.17.0`: persistent revisioned projects, project REST routes, transcript
  overrides, exports, and operator presets.
- `v0.16.0`: all twelve MCP tools and four resources live, with staged edits.
- `v0.15.0`: offline whisper.cpp transcription with a bundled tiny model.
- `v0.14.1`: sub-second durations, favicon, UI text, browser-verified flow.
- `v0.14.0`: ASR transcription endpoint and Transcribe card.
- `v0.13.0`: manual keep/discard overrides and inspector controls.
- `v0.12.0`: Shorts in jobs/API/UI with progress, logs, and MP4 downloads.
- `v0.11.0`: per-block telemetry, logs drawer, configurable rack, new UI.
- `v0.10.0`: vertical shorts engine (1080x1920, ASS captions), versioned assets.
- `v0.9.1`: AppImage starts the UI when opened with no arguments; AppImage
  contract tests.
- `v0.9.0`: Linux binary, AppImage, and Windows PE; transcript/cull API and UI
  inspector. Versioned asset names.
- `v0.8.0`: Linux binary, AppImage, and Windows PE. Local builds, no CI.
- `v0.7.0`: Linux x86_64, static FFmpeg. Artifact downloads and UI presets.
- `v0.6.0`: Linux x86_64, static FFmpeg. SRT retakes and LLM guard.
- `v0.5.0`: Linux x86_64, static FFmpeg. UI drives real jobs. Windows pending CI.
- `v0.4.0`: Linux x86_64, static FFmpeg, 168 MB. Windows pending CI.
