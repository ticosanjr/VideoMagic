# VideoFlow 2.58.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.58.0-linux-x86_64` — SHA-256 `734e76f30ab197f53d0f474ce0e1373660cc739c091c017bdd5595aea1038ba2`
- `VideoFlow-2.58.0-x86_64.AppImage` — SHA-256 `a66876f87079c768e37ecd14e66a0d47fa149e71623c96446e88ffa99b2720ca`
- `sbom.json` — SHA-256 `4c350ac298ed9c78e22a0712586ad06f4ff904b960a4b3049a4245ae59cf72cf`

## Run

Linux plain binary:

```bash
./videoflow-2.58.0-linux-x86_64 doctor
./videoflow-2.58.0-linux-x86_64 demo -o demo
./videoflow-2.58.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.58.0-x86_64.AppImage
./VideoFlow-2.58.0-x86_64.AppImage version
./VideoFlow-2.58.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
