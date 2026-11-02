# VideoFlow 2.28.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.28.0-linux-x86_64` — SHA-256 `9e323fc54438f483a5cf0cf0377b69d70df85f47e56e162ef0f3ab75e0ef282b`
- `VideoFlow-2.28.0-x86_64.AppImage` — SHA-256 `c68ecf8748c3a1f8c7881d24c3271f369c0235f68362668f84cff661d71198a9`
- `sbom.json` — SHA-256 `1479fa169e997b487acf799aefa6fe7d5555f59e806689429d0b5d82189fc5c0`

## Run

Linux plain binary:

```bash
./videoflow-2.28.0-linux-x86_64 doctor
./videoflow-2.28.0-linux-x86_64 demo -o demo
./videoflow-2.28.0-linux-x86_64 run input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.28.0-x86_64.AppImage
./VideoFlow-2.28.0-x86_64.AppImage version
./VideoFlow-2.28.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
