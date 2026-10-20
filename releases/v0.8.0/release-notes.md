# VideoFlow 0.8.0

Portable, model-free pre-edit pipeline.

## Artifacts

- `videoflow-0.8.0-linux-x86_64` — SHA-256 `95ddc043ef7c2c557752b839dad925cee84aef7de302aa0b669af6f86afb3f49`
- `VideoFlow-0.8.0-x86_64.AppImage` — SHA-256 `23fcb1f533f9685d8eea31d8e8262d5369ca006c1f32d17cc3badf77be5dfe3a`
- `videoflow-0.8.0-windows-x86_64.exe` — SHA-256 `03e231fb0bb37df127d72c4fc03dfc80c16dc50eac84b4f6c29017c1cf0ac121`

## Run

Linux plain binary:

```bash
./videoflow-0.8.0-linux-x86_64 doctor
./videoflow-0.8.0-linux-x86_64 demo -o demo
./videoflow-0.8.0-linux-x86_64 run input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-0.8.0-x86_64.AppImage
./VideoFlow-0.8.0-x86_64.AppImage version
./VideoFlow-0.8.0-x86_64.AppImage demo -o demo
```

Windows:

```powershell
.\videoflow-0.8.0-windows-x86_64.exe version
.\videoflow-0.8.0-windows-x86_64.exe doctor
.\videoflow-0.8.0-windows-x86_64.exe demo -o demo
```

## Notes

See `CHANGELOG.md`. Windows artifacts are PE32+ x86-64 and were built and
smoke-tested under Wine in this release.
