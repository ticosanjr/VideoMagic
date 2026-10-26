# VideoFlow 2.23.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.23.0-linux-x86_64` — SHA-256 `401ba93d7b2d4835c160980fedba77a9cb59b7e98a257b821ac2735e9d091243`
- `VideoFlow-2.23.0-x86_64.AppImage` — SHA-256 `e89e71a0b01190b43c484b699c988eb5693805d9d8878d75c98147c3220bed33`
- `sbom.json` — SHA-256 `d41f5b579ea0c17c5298c3804c6998286a8465f7be39ed16a94119e05632d5cb`

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
