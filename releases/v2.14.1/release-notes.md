# VideoFlow 2.14.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.14.1-linux-x86_64` — SHA-256 `a6e8d4e816c5154f6fd86d54ae18027b9538085fe599afbd23f2a9873bb69cff`
- `VideoFlow-2.14.1-x86_64.AppImage` — SHA-256 `33a68b3e243bdee84ce7ae3b3f5319845aab91f78de306c153c9b99638b97f47`
- `sbom.json` — SHA-256 `d269291dcbb2a042d4a7f74853d923b26790728406c8c94952b104f310614896`

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
