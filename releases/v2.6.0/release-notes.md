# VideoFlow 2.6.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.6.0-linux-x86_64` — SHA-256 `78beda52c7529b449dbfcdabea8d5339e95ab15eeaf0ff01f223e7ebab300d87`
- `VideoFlow-2.6.0-x86_64.AppImage` — SHA-256 `fa807ab40c09ae1da897e1bb0cf920666140d6bac3089b8732e7a7c8a9030d2b`
- `sbom.json` — SHA-256 `5aea73b34f72acfe62cf22187707f7ed6d99df98e591c5493bc2026202af376c`

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
