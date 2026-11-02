# VideoFlow 2.38.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.38.0-linux-x86_64` — SHA-256 `b1c476d9e030a7b2f61da742e78f4c45c53a86281ed643fa8723453ab58dea1c`
- `VideoFlow-2.38.0-x86_64.AppImage` — SHA-256 `6086d1da7f7e3a09fa1f8a10f3c063ff062e63e5614c31c2afb516715b9c22ec`
- `sbom.json` — SHA-256 `9b0185641895a55aa852bf70a1ef060dd54e72cbbc94ab8e34c0575988dd6fc2`

## Run

Linux plain binary:

```bash
./videoflow-2.38.0-linux-x86_64 doctor
./videoflow-2.38.0-linux-x86_64 demo -o demo
./videoflow-2.38.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.38.0-x86_64.AppImage
./VideoFlow-2.38.0-x86_64.AppImage version
./VideoFlow-2.38.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
