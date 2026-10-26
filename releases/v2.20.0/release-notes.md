# VideoFlow 2.20.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.20.0-linux-x86_64` — SHA-256 `706f481695978ec88dfcaba6113fab6edacb50cef37eab0d3e95411ccd3cca6a`
- `VideoFlow-2.20.0-x86_64.AppImage` — SHA-256 `3c72d3a28c62bdc3e7b7805e8efe092994b3de787515f45a4c2a4d9e295df07f`
- `sbom.json` — SHA-256 `74a37f18cc4aeb7c685cc33a01cfa93936a1bc4f6583770ba80a83871660127f`

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
