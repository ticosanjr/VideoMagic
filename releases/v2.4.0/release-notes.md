# VideoFlow 2.4.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.4.0-linux-x86_64` — SHA-256 `e809ca74d32af2f97963f7a5d3b950cc2feb65920b856ce9bd7ba8febb513046`
- `VideoFlow-2.4.0-x86_64.AppImage` — SHA-256 `6340f1b1303b263243ec8c291ce370280d2992fa08fe4a96f4a155e2390522f5`
- `sbom.json` — SHA-256 `a90bf1e82120d7788f1fbcc8fa42b613b5d15c2a2a6c37cde8dbd566a1ba3865`

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
