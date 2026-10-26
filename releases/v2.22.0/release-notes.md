# VideoFlow 2.22.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.22.0-linux-x86_64` — SHA-256 `8c083a18bee869706c98bca4d9acd327d9e806a863254e3e45342180705f77b6`
- `VideoFlow-2.22.0-x86_64.AppImage` — SHA-256 `40d5755b560096ada32156d4a4cdee4dc901de77e4c0a64e5ca46eaeac3ec9fb`
- `sbom.json` — SHA-256 `d6c5d470f10073022fe096a49c869bbe4422af45c57b7f493f539f6c52854c8b`

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
