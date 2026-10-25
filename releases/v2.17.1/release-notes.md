# VideoFlow 2.17.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.17.1-linux-x86_64` — SHA-256 `25b3308a860953d18ac2417ac390a510d79c4eae587d9194f73577dd8227f8ba`
- `VideoFlow-2.17.1-x86_64.AppImage` — SHA-256 `ebb7b9f75214a86756259b9668f3b271f5da6dd1cfa3f7d5148cf3be15f0e8f2`
- `sbom.json` — SHA-256 `c66bd097a5a7312bedf4ff3c88afa19a1f9be10660c051df95141835ce65a7b6`

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
