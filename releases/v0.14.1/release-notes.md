# VideoFlow 0.14.1

Portable, model-free pre-edit pipeline.

## Artifacts

- `videoflow-0.14.1-linux-x86_64` — SHA-256 `eb22f897c1c57a41527e4c07499330e2f53c5c9fe087ebc5e26140f5a9b50565`
- `VideoFlow-0.14.1-x86_64.AppImage` — SHA-256 `ad84ae7324826b7613bd19a78903f860fb74b1626e480909aa37c69ebb9ddc03`
- `videoflow-0.14.1-windows-x86_64.exe` — SHA-256 `faed524986371fadf15aa7357e5e7e09ce85ba08ca0365aa7effededb4325aa8`

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
