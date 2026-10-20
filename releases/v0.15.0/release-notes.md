# VideoFlow 0.15.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-0.15.0-linux-x86_64` — SHA-256 `f83e198bd95ecd1689d143d9bdbd923afa2e6b48d312adff320e48e3cb829e43`
- `VideoFlow-0.15.0-x86_64.AppImage` — SHA-256 `eb3010a3dac635acef2f4a4789785eaa69ef68717a9fb53bcb9b7a48e766cf61`
- `videoflow-0.15.0-windows-x86_64.exe` — SHA-256 `dcb27e1c7a829dd7a414879e68e720118cc75cf3d871784bb06f87332e622ee9`

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
