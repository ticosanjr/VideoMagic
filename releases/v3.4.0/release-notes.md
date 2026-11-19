# VideoFlow 3.4.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Opt-in hybrid GPU offload: ComputeRouter, VRAM budget, shared outputs,
  streaming upload, UDP discovery, and local fallback.
- Windows GPU worker kit with bootstrap, autostart, firewall, and personal
  pairing token.
- Setup -> GPU acceleration panel and live status pill.
- GPU-safe job telemetry, per-capability settings, and worker health/telemetry.

GPU speed certification (ASR/NVENC/matte) still requires a physical Windows
NVIDIA machine; see `docs/performance-3.4.md`. No personal Windows kit is
attached to this release.

## Artifacts

- `videoflow-3.4.0-linux-x86_64` — SHA-256 `ea34ae1980e5a178dc1a54dd9f545dc63ab46842e116d6b266a0a057ce81ce04`
- `VideoFlow-3.4.0-x86_64.AppImage` — SHA-256 `a07df1d165467e297fbdfe74100e862a4967cc588e93fed5d479e9906c1d1bdf`
- `sbom.json` — SHA-256 `8f14dd2f13e318ee9c0ff567926031352243f2eaeeec9d39ff33be8ccff0f8ca`
- `VideoFlow-3.4.0-linux-x86_64.tar.zst` — SHA-256 `a39d519f23dea5fb5330c0b19381ce6fa4ef86d2cdd4e1adb4041ba85217ce7d`
- `VideoFlow-3.4.0-mcp-servers.tar.zst` — SHA-256 `2fa6dafc8cb7a8c30b36e30c8afc4f62ba21683ae347fa9d432fd4ea63395cf4`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.4.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-3.4.0-linux-x86_64 doctor
./videoflow-3.4.0-linux-x86_64 recipe list
./videoflow-3.4.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.4.0-x86_64.AppImage
./VideoFlow-3.4.0-x86_64.AppImage version
./VideoFlow-3.4.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
