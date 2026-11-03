# VideoFlow 2.41.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.41.0-linux-x86_64` — SHA-256 `9b453a5010a1609a55697c66747fb53ce851e14db04b9d7af0089202ea5f427e`
- `VideoFlow-2.41.0-x86_64.AppImage` — SHA-256 `d721d445b0575de70f78bf43408c0cd1e446a8389f22fd345c0f985c137b2eb8`
- `sbom.json` — SHA-256 `c8c72404808421050bdb7edec8169b9d6e65c4836254c7b0f659883fc9e50a85`

## Run

Linux plain binary:

```bash
./videoflow-2.41.0-linux-x86_64 doctor
./videoflow-2.41.0-linux-x86_64 demo -o demo
./videoflow-2.41.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.41.0-x86_64.AppImage
./VideoFlow-2.41.0-x86_64.AppImage version
./VideoFlow-2.41.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
