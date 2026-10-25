# VideoFlow 2.10.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.10.0-linux-x86_64` — SHA-256 `869baced82d3d1dfa42dd646eebf1e85f7d2e076c6bf3720688218784d95e4e9`
- `VideoFlow-2.10.0-x86_64.AppImage` — SHA-256 `379be1f82731a359ddcd450c4d810cc51729424ece2e9ca164bedcb6f7f80b6a`
- `sbom.json` — SHA-256 `6e6f7d0f254e53a09996a61b491f7495c37738c19dab119b2f0063058f51c11a`

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
