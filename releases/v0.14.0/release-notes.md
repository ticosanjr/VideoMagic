# VideoFlow 0.14.0

Portable, model-free pre-edit pipeline.

## Artifacts

- `videoflow-0.14.0-linux-x86_64` — SHA-256 `c618c42351cdfb0daca7449be8e3c4f501aae146bb4b3eb4c350d8b70e320326`
- `VideoFlow-0.14.0-x86_64.AppImage` — SHA-256 `7286e8b8a7a70b62ce2ccdc377efb49bcf5f0e7d7a0d69bcd06c4dbf029d8b44`
- `videoflow-0.14.0-windows-x86_64.exe` — SHA-256 `c3b891069f13486d6b34279e68b867823ca0a9692f126e5326470608d353331c`

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
