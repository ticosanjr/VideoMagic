# VideoFlow 2.18.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.18.0-linux-x86_64` — SHA-256 `5d683950e6ab459f3b2a5dcbed70be421ae3553983e90d18f744e9edf33151ca`
- `VideoFlow-2.18.0-x86_64.AppImage` — SHA-256 `8687496ee97bb025003a38c2736c0af815fb20dff219cb0edef9497e88ca4fb3`
- `sbom.json` — SHA-256 `e6ecc16f31db504107ec32895753a8dbc965f1247e9437a123905a234d946d70`

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
