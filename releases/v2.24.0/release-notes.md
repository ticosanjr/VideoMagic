# VideoFlow 2.24.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.24.0-linux-x86_64` — SHA-256 `4d4a0541fa831cc3d9c4bb94267d8b73c33d16027171536cfac9a2587c93626f`
- `VideoFlow-2.24.0-x86_64.AppImage` — SHA-256 `792c88c1649682d317ee95d6da3021ddb658c0fe23bf76030bbf6e934406a9f5`
- `sbom.json` — SHA-256 `8f9b5abc1aced70c510e28f21809d292b77237dae37e61128e50cc10ad2809fc`

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
