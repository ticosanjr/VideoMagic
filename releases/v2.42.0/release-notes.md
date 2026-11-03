# VideoFlow 2.42.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.42.0-linux-x86_64` — SHA-256 `4a88f038ba4c8fea7c221af313d60402e2596e5745b72723325db315b47d0fdb`
- `VideoFlow-2.42.0-x86_64.AppImage` — SHA-256 `3823d57d4d0313d23321c5821f80c2d9eac0bbd47d139df5e59052f88426fd6c`
- `sbom.json` — SHA-256 `93126eb7929af657f9677b8e7e4bb06dbd2891f72a7d034a3142fdfb87cc8fed`

## Run

Linux plain binary:

```bash
./videoflow-2.42.0-linux-x86_64 doctor
./videoflow-2.42.0-linux-x86_64 demo -o demo
./videoflow-2.42.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.42.0-x86_64.AppImage
./VideoFlow-2.42.0-x86_64.AppImage version
./VideoFlow-2.42.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
