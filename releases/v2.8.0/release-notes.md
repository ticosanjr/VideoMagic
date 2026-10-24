# VideoFlow 2.8.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.8.0-linux-x86_64` — SHA-256 `e41d3413f3c16556dc3d30e4cbf5aef1683367d183ea180c8637d30a193fd687`
- `VideoFlow-2.8.0-x86_64.AppImage` — SHA-256 `161bbfad64a714e4ccbfa248662a67267676d32d535b7abffca56daa9d4e604a`
- `sbom.json` — SHA-256 `dafc54a8ea13e87427dd490882b2f82a7e01e29914fa623ac0ed6fcc1ceddf16`

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
