# VideoFlow 2.9.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.9.0-linux-x86_64` — SHA-256 `ccb8dc2b030e57fce183c97b894d4c90433ad5e7bf421a8f8fd4a9dcfb54b79b`
- `VideoFlow-2.9.0-x86_64.AppImage` — SHA-256 `3b0e86d456b57e722465f5c4dc99a0d9ee314a012689c9f0c481794f2a8a59a5`
- `sbom.json` — SHA-256 `13ebae5384e6ff93c617d719acd042b9fc5b4ac820ed06535126f5c9f5e257e1`

## Run

Linux plain binary:

```bash
./videoflow-linux-x86_64 doctor
./videoflow-linux-x86_64 demo -o demo
./videoflow-linux-x86_64 run input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-x86_64.AppImage
./VideoFlow-x86_64.AppImage version
./VideoFlow-x86_64.AppImage demo -o demo
```

Windows:

```powershell
.\videoflow-windows-x86_64.exe version
.\videoflow-windows-x86_64.exe doctor
.\videoflow-windows-x86_64.exe demo -o demo
```

## Notes

See `CHANGELOG.md`. Windows artifacts are PE32+ x86-64 and were built and
smoke-tested under Wine in this release.
