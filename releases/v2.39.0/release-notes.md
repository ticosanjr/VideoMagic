# VideoFlow 2.39.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.39.0-linux-x86_64` — SHA-256 `29613cb0dd504814948b4017b7c1d226f524afddd98459ac0dee0de3cf4d6718`
- `VideoFlow-2.39.0-x86_64.AppImage` — SHA-256 `56f07fbc80a0c9567480b8bd6d8ff52a8b14ad85a78dfa7395beb873a5ed1356`
- `sbom.json` — SHA-256 `5d0c8ac1e67a250fd0b6bff28d83cf1820e810fcc4b13997799d446b04b5dec8`

## Run

Linux plain binary:

```bash
./videoflow-2.39.0-linux-x86_64 doctor
./videoflow-2.39.0-linux-x86_64 demo -o demo
./videoflow-2.39.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.39.0-x86_64.AppImage
./VideoFlow-2.39.0-x86_64.AppImage version
./VideoFlow-2.39.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
