# VideoFlow 2.58.3

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.58.3-linux-x86_64` — SHA-256 `a9c79ab28f5b6a09038dd7b934cd0dbcf309ee7fee174dfc91a1b41727b86bd7`
- `VideoFlow-2.58.3-x86_64.AppImage` — SHA-256 `3dac4a6794612cb5701b0c51fc49cffb3c947e93ad3a6905c0285da1c488b4b4`
- `sbom.json` — SHA-256 `0355e98d46908e74fc260c4a5a5b01b1f2d31d32a101d01df60ab12e0b5c50c4`

## Run

Linux plain binary:

```bash
./videoflow-2.58.3-linux-x86_64 doctor
./videoflow-2.58.3-linux-x86_64 demo -o demo
./videoflow-2.58.3-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.58.3-x86_64.AppImage
./VideoFlow-2.58.3-x86_64.AppImage version
./VideoFlow-2.58.3-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
