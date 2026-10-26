# VideoFlow 2.21.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.21.0-linux-x86_64` — SHA-256 `2ea3454740c313b4d4bd647604e6a330f3b25be8fc96d118e9e68217fdf6b9c4`
- `VideoFlow-2.21.0-x86_64.AppImage` — SHA-256 `522807cafc6616305c05702e339371832a9b35f58f7dbff390c931da13020322`
- `sbom.json` — SHA-256 `403011a36a209528d6fa9013f2c3c6696cddd269c1fb8c9fd856845a32d767cb`

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
