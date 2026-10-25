# VideoFlow 2.15.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.15.0-linux-x86_64` — SHA-256 `2f0c0007edf88c531d2b336458592673f4a804ea84528d4382294ded92c8bf66`
- `VideoFlow-2.15.0-x86_64.AppImage` — SHA-256 `75e7ddb3242bcdd71c27d70608805ca96b312d1b25db20ba8e19620466d0eeeb`
- `sbom.json` — SHA-256 `aa0c27454ea297c53dc33c9d8ad355f783f7a13493795b8e6c81c0d2f3a981b7`

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
