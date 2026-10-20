# VideoFlow 0.10.0

Portable, model-free pre-edit pipeline.

## Artifacts

- `videoflow-0.10.0-linux-x86_64` — SHA-256 `1fa15eb39a190ba96538a47f3e2411ad57594cc9e030019e52833ccbb8e05d17`
- `VideoFlow-0.10.0-x86_64.AppImage` — SHA-256 `439da5eeb575299b92df802670271f37d772ebb2f87f1cb9070ec4446130a3d0`
- `videoflow-0.10.0-windows-x86_64.exe` — SHA-256 `6bfb1c544bc1c52a8fe20f8249bbcb44f1d3e1a942e59f26947ffb4b131c4849`

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
