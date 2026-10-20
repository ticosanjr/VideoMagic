# VideoFlow 0.9.1

Portable, model-free pre-edit pipeline.

## Artifacts

- `videoflow-0.9.1-linux-x86_64` — SHA-256 `28624852cf938321947c301e248c75d2e5ba3427aeeb3d3c3a829b93e1e1bddc`
- `VideoFlow-0.9.1-x86_64.AppImage` — SHA-256 `ad12ed4cddd9a098361d4bcfc9649f40443f3840d04d350d2c06c6c3c09a4306`
- `videoflow-0.9.1-windows-x86_64.exe` — SHA-256 `01654f3deb184d37d8cd7ebeb1572b176922b2c5f3572cf047a380148934c6e6`

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
