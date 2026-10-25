# VideoFlow 2.12.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.12.0-linux-x86_64` — SHA-256 `e603074d6016c624ca0bce1b7544a07af8af4f8eaaf665d19291501ce4f12736`
- `VideoFlow-2.12.0-x86_64.AppImage` — SHA-256 `6c07886b4853e9722467d0d22291c8af8c765d4d80f9e98433e5408a12bc6383`
- `sbom.json` — SHA-256 `2ee65227cf49bd304fac56169839b88de59e355cef08cbf685a29d0babbe5407`

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
