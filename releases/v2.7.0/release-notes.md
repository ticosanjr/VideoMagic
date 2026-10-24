# VideoFlow 2.7.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.7.0-linux-x86_64` — SHA-256 `fe48b5fa72e6bc3a4dbc98544a2adb9349c316ebda4a3ae8b15a3c2c0cd0218e`
- `VideoFlow-2.7.0-x86_64.AppImage` — SHA-256 `c8121c17e4805afe273e7de661b698a15bb49d95a6a1d28174f658dcdb67f90f`
- `sbom.json` — SHA-256 `5cc73111d602db9ee1772a977c2e7cb79694844f8c43350276eb627c957f9f30`

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
