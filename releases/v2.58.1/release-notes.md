# VideoFlow 2.58.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.58.1-linux-x86_64` — SHA-256 `8dc9fdbdd9d8517ab411c777c27251f6f2bed79f5191a29f1bab5447cfc97ae0`
- `VideoFlow-2.58.1-x86_64.AppImage` — SHA-256 `33c7bc5711a499d44bb0d3feb018a48f74a51af5459f037aaaf20ddff8930185`
- `sbom.json` — SHA-256 `631069e970b1d9f49a801ca3277ef37257e2ec951d5af4c682e3ce33286f6880`

## Run

Linux plain binary:

```bash
./videoflow-2.58.1-linux-x86_64 doctor
./videoflow-2.58.1-linux-x86_64 demo -o demo
./videoflow-2.58.1-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.58.1-x86_64.AppImage
./VideoFlow-2.58.1-x86_64.AppImage version
./VideoFlow-2.58.1-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
