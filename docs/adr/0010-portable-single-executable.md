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
- Build each artifact on its own OS; CI runs `ubuntu-22.04` and
  `windows-latest`.
- Add a unified CLI: `run`, `serve`, `mcp`, `doctor`, `demo`, `version`.
- Add a model-free pipeline path: FFmpeg `silencedetect` for speech intervals,
  then the deterministic timeline and exporters. This makes the portable binary
  useful without model downloads.
- Store portable data next to the executable unless `VIDEOWFLOW_HOME` overrides.
- Resolve binaries from the bundle, next to the executable, then `PATH`, with
  `VIDEOWFLOW_FFMPEG` / `VIDEOWFLOW_FFPROBE` overrides.

## Consequences

- Linux and Windows need separate builds and separate smoke tests.
- A Linux binary is tied to the build host's glibc. Ubuntu 22.04 is the baseline.
- Bundling FFmpeg adds roughly 170 MB compressed and brings FFmpeg's license
  obligations; bundling is an explicit build flag.
- The portable path is lower quality than Silero VAD. It is a fallback, not a
  replacement, and the docs say so.
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
