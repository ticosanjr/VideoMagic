# VideoFlow 2.49.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.49.0-linux-x86_64` — SHA-256 `6c07cc39d8348f344e28a1b9422966e61371b7c5d9d2b7bbc2fbe46f92ab583e`
- `VideoFlow-2.49.0-x86_64.AppImage` — SHA-256 `c82ddd14a80bee03033b2965d3da081f9e53a60e44fa50bc165ac9895ab9da9d`
- `sbom.json` — SHA-256 `7f7b674b807942d80382b8eb9d40cf66efac00ce0b44254cedab5987e1e6972e`

## Run

Linux plain binary:

```bash
./videoflow-2.49.0-linux-x86_64 doctor
./videoflow-2.49.0-linux-x86_64 demo -o demo
./videoflow-2.49.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.49.0-x86_64.AppImage
./VideoFlow-2.49.0-x86_64.AppImage version
./VideoFlow-2.49.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
