# VideoFlow 2.48.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.48.0-linux-x86_64` — SHA-256 `8b6b8cc7205280b28044fd6dc7aa63cce64f527e2ae2df6968648b5d371bec5d`
- `VideoFlow-2.48.0-x86_64.AppImage` — SHA-256 `227225e85eb0eabcca6f87f5c17effc656213ba5c7e15b5833a376666c84e0e8`
- `sbom.json` — SHA-256 `96ef26f491da2c11437a823e949aff8d69f45de97523f7fdf057dbaffee79802`

## Run

Linux plain binary:

```bash
./videoflow-2.48.0-linux-x86_64 doctor
./videoflow-2.48.0-linux-x86_64 demo -o demo
./videoflow-2.48.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.48.0-x86_64.AppImage
./VideoFlow-2.48.0-x86_64.AppImage version
./VideoFlow-2.48.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
