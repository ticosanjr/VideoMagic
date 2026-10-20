# ADR-0010 — One portable executable per OS

Status: accepted. Date: 2026-10-19.

## Context

The product should be usable without installing Python, Node, or FFmpeg, and
should run from a folder or USB stick on Linux and Windows. The pipeline is
Python, the UI is Svelte, and the media engine is FFmpeg. A single file cannot be
both an ELF and a PE binary, and PyInstaller does not cross-compile.

## Decision

- Ship one console executable per OS (`videoflow` / `videoflow.exe`).
- Bundle Python, dependencies, presets, the built UI, and optionally
  FFmpeg/FFprobe with PyInstaller onefile. Use the BtbN static GPL builds so the
  media binaries do not depend on the host's codec libraries.
- Build Linux natively and the Windows PE locally with Wine WoW64 plus the
  Windows embeddable Python. No GitHub Actions workflow is used.
- Also wrap the Linux binary in an AppImage for a single-file desktop artifact.
- Add a unified CLI: `run`, `serve`, `mcp`, `doctor`, `demo`, `version`.
- Add a model-free pipeline fallback: FFmpeg `silencedetect` for speech
  intervals, then the deterministic timeline and exporters. From 0.18, release
  builds also bundle Silero VAD and ONNX Runtime; FFmpeg remains the fallback.
  From 0.19, release builds bundle Faster-Whisper, CTranslate2, PyAV, and the
  pinned small model; whisper.cpp remains the fallback.
- Store portable data next to the executable unless `VIDEOWFLOW_HOME` overrides.
- Resolve binaries from the bundle, next to the executable, then `PATH`, with
  `VIDEOWFLOW_FFMPEG` / `VIDEOWFLOW_FFPROBE` overrides.

## Consequences

- Linux and Windows need separate builds and separate smoke tests.
- The Windows PE is validated under Wine; a native Windows pass is still
  recommended.
- A Linux binary is tied to the build host's glibc. Build on the oldest distro
  you intend to support.
- Bundling FFmpeg adds roughly 170 MB compressed and brings FFmpeg's license
  obligations; bundling is an explicit build flag.
- The FFmpeg fallback is lower quality than Silero VAD. Release builds bundle
  Silero by default; builds without it still run, at lower VAD quality.
- The UI can be served from the same process and is found through `_MEIPASS`.
- Signing is not configured. Windows will show SmartScreen warnings until a
  certificate exists.

## Alternatives rejected

- A zipapp or wheel: still needs Python.
- One binary for both OSes: not possible with native bootloaders.
- Downloading FFmpeg on first run: not offline-portable.
- Requiring a system FFmpeg: fewer bytes, but the user asked for one portable
  file and offline use.
- Nuitka: viable, but PyInstaller is simpler for this dependency set.
