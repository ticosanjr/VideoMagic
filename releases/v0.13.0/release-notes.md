# VideoFlow 0.13.0

Portable, model-free pre-edit pipeline.

## Artifacts

- `videoflow-0.13.0-linux-x86_64` — SHA-256 `2dbdc9328b4bba442dd86343ecaa6eba1e810fa9d8bb5e31582a6189f24d37ad`
- `VideoFlow-0.13.0-x86_64.AppImage` — SHA-256 `38874c67adf7ad70bc00a5c3ad37a5a009dad413d50039a3d7ece12418c24847`
- `videoflow-0.13.0-windows-x86_64.exe` — SHA-256 `e77add77fc1ed1c79b29c8a07dc3cdddebeb0240a910f159c46b973a6357c49e`

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
