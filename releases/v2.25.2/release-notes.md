# VideoFlow 2.25.2

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.25.2-linux-x86_64` — SHA-256 `2b06b3579d07e4f841005af3c301113ea76295766e48a9f73ed64424de91af7f`
- `VideoFlow-2.25.2-x86_64.AppImage` — SHA-256 `579707f72e3ff7fe698c21bc9096bf03b735d4f5dfc16cea42ef182cf244a4e7`
- `sbom.json` — SHA-256 `9f55a4fca5eb89fa3454347edef1719d0708c6ee3d048dac6a3f51af3ef19750`

## Run

Linux plain binary:

```bash
./videoflow-2.25.2-linux-x86_64 doctor
./videoflow-2.25.2-linux-x86_64 demo -o demo
./videoflow-2.25.2-linux-x86_64 run input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.25.2-x86_64.AppImage
./VideoFlow-2.25.2-x86_64.AppImage version
./VideoFlow-2.25.2-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
