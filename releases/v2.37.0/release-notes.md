# VideoFlow 2.37.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.37.0-linux-x86_64` — SHA-256 `7d9eafef6159a94b52ec17f74344ef0544e36fa9b0e1c0fd48d4455e59cb7368`
- `VideoFlow-2.37.0-x86_64.AppImage` — SHA-256 `aebc7bd2701dd8d39932ba7e77935d0b088a9dee1aff069ab5e9cf18706dd916`
- `sbom.json` — SHA-256 `63c0c60f2b0ca9a789a4feb1fd5f5b723579a3484fc3964159951f2053a5dae4`

## Run

Linux plain binary:

```bash
./videoflow-2.37.0-linux-x86_64 doctor
./videoflow-2.37.0-linux-x86_64 demo -o demo
./videoflow-2.37.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.37.0-x86_64.AppImage
./VideoFlow-2.37.0-x86_64.AppImage version
./VideoFlow-2.37.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
