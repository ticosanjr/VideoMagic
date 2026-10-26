# VideoFlow 2.19.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.19.0-linux-x86_64` — SHA-256 `1e6389362d57aa415a9c8dce8ee30827439754254d86873ab170b88a2fbb077c`
- `VideoFlow-2.19.0-x86_64.AppImage` — SHA-256 `3a67bb3757ac1bf4caf2db08d103d7ae2e0a85a2f63ce20b910532ba9373508c`
- `sbom.json` — SHA-256 `e1dd5c05f0c377e211e1b1a54561064f05fc3f741c8f748e88429859ba7d49ba`

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
