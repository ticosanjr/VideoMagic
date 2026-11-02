# VideoFlow 2.32.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.32.1-linux-x86_64` — SHA-256 `d4048a779364487cb90184353f2373be941073e6e14e26b9d79bbe6b9304ac7f`
- `VideoFlow-2.32.1-x86_64.AppImage` — SHA-256 `0c28e4c554a411c0845a690218586eeb6fa9bef999b7e44c2f549607db373a6b`
- `sbom.json` — SHA-256 `407514ac013f48f3df4ca30f5324971018bd669ebb5d17233cce4e43d7164f1d`

## Run

Linux plain binary:

```bash
./videoflow-2.32.1-linux-x86_64 doctor
./videoflow-2.32.1-linux-x86_64 demo -o demo
./videoflow-2.32.1-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.32.1-x86_64.AppImage
./VideoFlow-2.32.1-x86_64.AppImage version
./VideoFlow-2.32.1-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
