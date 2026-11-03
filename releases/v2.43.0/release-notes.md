# VideoFlow 2.43.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.43.0-linux-x86_64` — SHA-256 `e3624be8ccdb8b89ebc625c5343e43f686ef394e34b730cb9bc14adedcc6ced7`
- `VideoFlow-2.43.0-x86_64.AppImage` — SHA-256 `b595a74099d5749a5988a4ee72431885540b33b0c52ece7758f895743a0c95c6`
- `sbom.json` — SHA-256 `d9af15914dbb9157ff95c8c2c07aa6409d8a872a5ee28ad38cdc4197f01debfe`

## Run

Linux plain binary:

```bash
./videoflow-2.43.0-linux-x86_64 doctor
./videoflow-2.43.0-linux-x86_64 demo -o demo
./videoflow-2.43.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.43.0-x86_64.AppImage
./VideoFlow-2.43.0-x86_64.AppImage version
./VideoFlow-2.43.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
