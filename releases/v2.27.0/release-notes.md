# VideoFlow 2.27.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.27.0-linux-x86_64` — SHA-256 `a8119d9c06f76e776b29c06c1b28e6fd13bd07768c952d81a71d8a4e3062f0ff`
- `VideoFlow-2.27.0-x86_64.AppImage` — SHA-256 `a9840bf7c0b711eb6898a6b500b0ece8d90a4736a68f9fcf6068dcb79b0343f4`
- `sbom.json` — SHA-256 `c785b81087f07147bc82be81c35b1cebbf95cde1136e18641ccbb1534c8153b9`

## Run

Linux plain binary:

```bash
./videoflow-2.27.0-linux-x86_64 doctor
./videoflow-2.27.0-linux-x86_64 demo -o demo
./videoflow-2.27.0-linux-x86_64 run input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.27.0-x86_64.AppImage
./VideoFlow-2.27.0-x86_64.AppImage version
./VideoFlow-2.27.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
