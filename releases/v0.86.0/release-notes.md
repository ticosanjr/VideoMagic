# VideoFlow 0.86.0 beta

Local-first beta built locally on Linux. GitHub Actions is not used.

## Settings Hub

- `settings.json` with runtime, paths, models, automation, quality, UI, LLM,
  speech, TTS, stock, and translation sections.
- Export, import, reset, environment overrides, and restart-required markers.
- Settings now influence job workers/history, allowed roots, cache/model dirs,
  FFmpeg resolution, scheduler interval, LLM controls, and TTS/stock defaults.

## Models

- Expanded ASR catalog: Faster-Whisper tiny/base/small/medium/large-v3 and
  whisper.cpp base/small/medium.
- Default model per capability.
- Device, compute type, and thread settings.
- Local model registration without downloading.
- File and checksum verification.

## Services

- SQLite-backed service definitions.
- Start/stop, health checks, autostart, and per-service logs.
- Works with Ollama, LM Studio, whisper.cpp server, Piper, ComfyUI, or any
  local command.

## Library

- Brand templates.
- Project templates.
- Presets.
- Fonts, images, and music uploads.

## Diagnostics

- Doctor now checks FFmpeg capabilities, CUDA/ONNX providers, SQLite integrity,
  providers, service definitions, models, disk, and settings.
- Support bundle ZIP with redacted environment values.

## Validation

- 467 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.
- Linux binary and AppImage verified locally.

## Notes

- Distribution, signing, macOS packaging, and Windows cross-builds remain out
  of scope.
- Manual NLE QA and per-clip waveforms remain future work.
