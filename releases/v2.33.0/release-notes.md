# VideoFlow 2.33.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.33.0-linux-x86_64` — SHA-256 `890dfcc204d846c0a8e89ed025220d78d013d971419fa9f25462d227ab69395e`
- `VideoFlow-2.33.0-x86_64.AppImage` — SHA-256 `a6bb5246c0a3d768c9aa60581293f5188d8690ecc4ad5820e9bdd02bc42b388b`
- `sbom.json` — SHA-256 `71128a589cd53e4983300b8d7d03eb75b69766f9dc592b342d3bf3b070485162`

## Run

Linux plain binary:

```bash
./videoflow-2.33.0-linux-x86_64 doctor
./videoflow-2.33.0-linux-x86_64 demo -o demo
./videoflow-2.33.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.33.0-x86_64.AppImage
./VideoFlow-2.33.0-x86_64.AppImage version
./VideoFlow-2.33.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
