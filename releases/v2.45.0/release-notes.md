# VideoFlow 2.45.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.45.0-linux-x86_64` — SHA-256 `bbbceb6aebad44d17d040ddaf9c0883dc6680dfd0c6ac30398dd146f58e869f0`
- `VideoFlow-2.45.0-x86_64.AppImage` — SHA-256 `3fd2350abb79ffc866a768a35c90fabd6bc19674a6d7cfc71a10a0b35246cfed`
- `sbom.json` — SHA-256 `92b6e2ca09ac30b0766da06469e77fc1d18cec59608564a3e7d280270a8d62ce`

## Run

Linux plain binary:

```bash
./videoflow-2.45.0-linux-x86_64 doctor
./videoflow-2.45.0-linux-x86_64 demo -o demo
./videoflow-2.45.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.45.0-x86_64.AppImage
./VideoFlow-2.45.0-x86_64.AppImage version
./VideoFlow-2.45.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
