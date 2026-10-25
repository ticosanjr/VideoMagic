# VideoFlow 2.15.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.15.1-linux-x86_64` — SHA-256 `aa1510e65a52f1d0b80bfd20c33c21445968f5a8918949e70948f88e5d4b9175`
- `VideoFlow-2.15.1-x86_64.AppImage` — SHA-256 `43128c4ce8a20323f2c18b4bae989cb94a0ac0a418335b88c4a19dace983bf14`
- `sbom.json` — SHA-256 `f4ee6a5cadcce89082b4bef86fe30f88a5d615ae75268d97b98dd1e2706cb6dc`

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
