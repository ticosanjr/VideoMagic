# VideoFlow 2.17.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.17.0-linux-x86_64` — SHA-256 `5c44a4dc6b27a3aac978c720df019c390f0698f3f39f5cb2b7a39e9f8a91c21f`
- `VideoFlow-2.17.0-x86_64.AppImage` — SHA-256 `948f262a9e2644d5e3031015526ef04a8dddb62546bff514cf537dd1340e95d3`
- `sbom.json` — SHA-256 `8d8511f8d3947d81df6ceefdf4ffb1ac73ab5a2ae52068590a46d797fef1dac9`

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
