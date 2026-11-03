# VideoFlow 2.51.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.51.0-linux-x86_64` — SHA-256 `18e31a8d980c4046bc9bc9f6a6731c6287833da81c00620ea64bf9e8e1019589`
- `VideoFlow-2.51.0-x86_64.AppImage` — SHA-256 `4ac8b837ea329249e672fdc8ef744e749e3538aea63280b6d24167f78738fc07`
- `sbom.json` — SHA-256 `d0828c54687800679f259eef0a3de7ef784614ccc89cc7ee4f6be4a4ad59f739`

## Run

Linux plain binary:

```bash
./videoflow-2.51.0-linux-x86_64 doctor
./videoflow-2.51.0-linux-x86_64 demo -o demo
./videoflow-2.51.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.51.0-x86_64.AppImage
./VideoFlow-2.51.0-x86_64.AppImage version
./VideoFlow-2.51.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
