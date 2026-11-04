# VideoFlow 2.57.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.57.0-linux-x86_64` — SHA-256 `48d9bfd87750a0ccefc5d0842ded95f861169d756a612ad2496462204d91c1a9`
- `VideoFlow-2.57.0-x86_64.AppImage` — SHA-256 `1e98dce3bdd93d5fc9b0240be7ec9f0d0d9d708f8430e860b288a3463ee16d0a`
- `sbom.json` — SHA-256 `71fdfed2ddc3588b0585c7a2a0b7b5ffb474de86f2e6408237d84a9b0d23b61a`

## Run

Linux plain binary:

```bash
./videoflow-2.57.0-linux-x86_64 doctor
./videoflow-2.57.0-linux-x86_64 demo -o demo
./videoflow-2.57.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.57.0-x86_64.AppImage
./VideoFlow-2.57.0-x86_64.AppImage version
./VideoFlow-2.57.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
