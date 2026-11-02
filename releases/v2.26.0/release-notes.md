# VideoFlow 2.26.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.26.0-linux-x86_64` — SHA-256 `5b394f4379115f9677a2764b05fe18d1d101a15ab7ea68fdc22d1b3b6497e268`
- `VideoFlow-2.26.0-x86_64.AppImage` — SHA-256 `57f52b8b3080b737e796d74329920a462b44e20e1f941664fc63b5e38138caeb`
- `sbom.json` — SHA-256 `53f967707ebd70428189a47624082f087d383e4880695cd2177b6135aa31b29b`

## Run

Linux plain binary:

```bash
./videoflow-2.26.0-linux-x86_64 doctor
./videoflow-2.26.0-linux-x86_64 demo -o demo
./videoflow-2.26.0-linux-x86_64 run input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.26.0-x86_64.AppImage
./VideoFlow-2.26.0-x86_64.AppImage version
./VideoFlow-2.26.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
