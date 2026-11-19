# VideoFlow 3.5.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Consolidated the core MCP surface from 43 to 33 tools. Each workflow area
  now has one tool with explicit actions: style, job, export, assets, and
  overlay preview.
- Media contract for 48 kHz/24-bit audio, alpha overlays, exact rational frame
  rates, color metadata, and one-frame duration checks.
- `audio.finalize` with two-pass linear loudness, mono repair, music ducking,
  Foley mix, and 48 kHz/24-bit output.
- HTTP-first GPU transport with resumable uploads/downloads, SHA-256, Range
  resume, artifact manifests, and automatic shared-mount fallback.
- Windows kit with one `VideoFlowGPU.bat` entry point, offline worker wheels,
  full traceback capture, a never-closing menu, and a supervisor with watchdog.
- `gpu.json` cross-process configuration, `vf_gpu_preflight`, and a real
  `/probe` for CUDA/NVENC/ASR/matte.
- Multi-source ingest, strict `ShortsClipSpec`, OpenCode session brief,
  transcript query, glossary, storyboard strip, preflight plan, and named
  checkpoints.
- Immutable per-artifact QA reports, `vf_qa_compare`, fast-mode loudness/caption
  checks, and transcript-derived release titles.
- Eight short contract documents exposed as `vf://docs/contracts/*`.

## Known limitations

- Physical ASR/NVENC/matte speed certification on Windows/NVIDIA hardware is
  still pending. No speedup is claimed without a real RTX 3060 run. See
  `docs/qa-evidence/3.5.0-gpu.json`.
- The Linux artifacts are not code-signed.

## Artifacts

- `videoflow-3.5.0-linux-x86_64` — SHA-256 `f560b915bd0f5e1be8f20d0b1ccbf08b6984e4786212fbb801f296482a5742a8`
- `VideoFlow-3.5.0-x86_64.AppImage` — SHA-256 `6ec5dcbf13c237198a6218995bb695da99b57d3cff8baa4818570a93ea504bab`
- `sbom.json` — SHA-256 `fb1602c52cc0612d58f489fa06a3b23161b0da0d28e115b93744a6fa617448ff`
- `VideoFlow-3.5.0-linux-x86_64.tar.zst` — SHA-256 `a1cc372df06a727d793af6b826f9ae9d67e3878f763693aeac0c00be5b291e8e`
- `VideoFlow-3.5.0-mcp-servers.tar.zst` — SHA-256 `f0e40b543a44462b33d6a1dc3f3fd356eb2e7e2d704f123c357d104385a334dc`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.5.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-3.5.0-linux-x86_64 doctor
./videoflow-3.5.0-linux-x86_64 recipe list
./videoflow-3.5.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.5.0-x86_64.AppImage
./VideoFlow-3.5.0-x86_64.AppImage version
./VideoFlow-3.5.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
