# VideoFlow 2.58.8

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.58.8-linux-x86_64` — SHA-256 `d31c38ff4e69e25fc81ad6f3d2b33ddd54bb3b8a259f82e56c173aa236c91877`
- `VideoFlow-2.58.8-x86_64.AppImage` — SHA-256 `effd64f9b8528366d5a5690dc91dde2a43ebaec1943028d95f4fed05f7bac655`
- `sbom.json` — SHA-256 `3135279b43423da985c4e1f61ce374dd6a80848d37fa23fbb96395f86c1f3776`

## Run

Linux plain binary:

```bash
./videoflow-2.58.8-linux-x86_64 doctor
./videoflow-2.58.8-linux-x86_64 demo -o demo
./videoflow-2.58.8-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.58.8-x86_64.AppImage
./VideoFlow-2.58.8-x86_64.AppImage version
./VideoFlow-2.58.8-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
