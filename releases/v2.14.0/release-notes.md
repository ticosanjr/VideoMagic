# VideoFlow 2.14.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.14.0-linux-x86_64` — SHA-256 `b07b9eaef32a0fad6fa395b1eb698fa08d8587da02b7e58d351371f7cdded3e1`
- `VideoFlow-2.14.0-x86_64.AppImage` — SHA-256 `a3a0b545f342eaea66f356296f92766e5cf94901c48e3d6090e93d7458be432b`
- `sbom.json` — SHA-256 `2e62d1d0433fa132fb667c68daeadd3f08ba0df6606638f949c1867ba5d55607`

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
