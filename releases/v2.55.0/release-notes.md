# VideoFlow 2.55.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.55.0-linux-x86_64` — SHA-256 `237ad61628e874df89293d48076e3dcc8407f0fe29e4cd4a4e6fc4c7d512da01`
- `VideoFlow-2.55.0-x86_64.AppImage` — SHA-256 `8092dc24bf6113dd2a3c1d104e14c458f26199ee2f98426000c851159a7ca8c8`
- `sbom.json` — SHA-256 `81a1b26173e1a2a785e1ee5ba3fa778317c6be4bc53625e08caa93971c1deae7`

## Run

Linux plain binary:

```bash
./videoflow-2.55.0-linux-x86_64 doctor
./videoflow-2.55.0-linux-x86_64 demo -o demo
./videoflow-2.55.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.55.0-x86_64.AppImage
./VideoFlow-2.55.0-x86_64.AppImage version
./VideoFlow-2.55.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
