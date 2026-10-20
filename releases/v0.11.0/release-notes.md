# VideoFlow 0.11.0

Portable, model-free pre-edit pipeline.

## Artifacts

- `videoflow-0.11.0-linux-x86_64` — SHA-256 `6ad61f35aff2f8f4c1f9b8cf06a1d0cc8725435fcfc23159b777a2a9f1a6adf6`
- `VideoFlow-0.11.0-x86_64.AppImage` — SHA-256 `56807a42c009697a3709b6f8d88219666aaa76172397106791438085d22af9f2`
- `videoflow-0.11.0-windows-x86_64.exe` — SHA-256 `4f2af1b2f37156ecafe030d8047bcbac181c2a90f6bacdc10301096d428e30aa`

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
