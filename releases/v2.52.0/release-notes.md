# VideoFlow 2.52.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.52.0-linux-x86_64` — SHA-256 `e94813439fda6f119c1c36a7bdcd030a96678ec098fc952b0b37f83a590e569b`
- `VideoFlow-2.52.0-x86_64.AppImage` — SHA-256 `98b119776c64dd3e5149e1a3aaf618785e0a4d3f991f48f83774f1eaf69e665e`
- `sbom.json` — SHA-256 `f811226e4dd30612371117f983f329c9942e8f48d27aa513bbe30c02636b3bbf`

## Run

Linux plain binary:

```bash
./videoflow-2.52.0-linux-x86_64 doctor
./videoflow-2.52.0-linux-x86_64 demo -o demo
./videoflow-2.52.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.52.0-x86_64.AppImage
./VideoFlow-2.52.0-x86_64.AppImage version
./VideoFlow-2.52.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
