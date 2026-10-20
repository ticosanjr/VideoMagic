# VideoFlow 0.12.0

Portable, model-free pre-edit pipeline.

## Artifacts

- `videoflow-0.12.0-linux-x86_64` — SHA-256 `34b9238ecc57da427cc8ae11d68723d17455eb0088057d86eb10f22a816aded8`
- `VideoFlow-0.12.0-x86_64.AppImage` — SHA-256 `03f51eb2aebe3faab72b3430fc12f2639d3227c4d4556aaf1b03d1bc2c7827ba`
- `videoflow-0.12.0-windows-x86_64.exe` — SHA-256 `70a2d3b71266c0c549d8c4f8cbd7b582155788a7101392aff1e217046103609d`

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
