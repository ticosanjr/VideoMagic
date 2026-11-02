# VideoFlow 2.32.2

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.32.2-linux-x86_64` — SHA-256 `54d5618aca0d6071bc2bd05b59fdae5c0fbdfde985110c9a734f2ad2beccea69`
- `VideoFlow-2.32.2-x86_64.AppImage` — SHA-256 `fe328bbbd2bd60ed1a699c7db36bdb03c65beffb0b8b45857e4b70f73ba2d854`
- `sbom.json` — SHA-256 `de9c8ae914ea137eae1fc94c0946906dc545a8d38b49285bb59808e7f9eb9fa1`

## Run

Linux plain binary:

```bash
./videoflow-2.32.2-linux-x86_64 doctor
./videoflow-2.32.2-linux-x86_64 demo -o demo
./videoflow-2.32.2-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.32.2-x86_64.AppImage
./VideoFlow-2.32.2-x86_64.AppImage version
./VideoFlow-2.32.2-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
