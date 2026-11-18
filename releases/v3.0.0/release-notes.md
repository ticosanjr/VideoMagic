# VideoFlow 3.0.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-3.0.0-linux-x86_64` — SHA-256 `32e124630dc6a01c54fb7b4e0498a8d752d35c424bac78485e0c6bb054474c30`
- `VideoFlow-3.0.0-x86_64.AppImage` — SHA-256 `e02bc09990ee7eee2d36f846c7fe7031f06a2f3ab43990539538d9383f29fe14`
- `VideoFlow-3.0.0-linux-x86_64.tar.zst` — SHA-256 `f8b6b3501bdfe018dbe83f1ed52e5d55930929729431648e37be25c0d6e09a3b`
- `VideoFlow-3.0.0-mcp-servers.tar.zst` — SHA-256 `e6df913af6ef4f71128b54c74a5046a7375346114fa8dae722d637ea697f1e28`
- `sbom.json` — SHA-256 `5bc63c0925bc848a58b8060965103cfdc1b5b914f5883342eeb51e2a26d30068`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.0.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-3.0.0-linux-x86_64 doctor
./videoflow-3.0.0-linux-x86_64 recipe list
./videoflow-3.0.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.0.0-x86_64.AppImage
./VideoFlow-3.0.0-x86_64.AppImage version
./VideoFlow-3.0.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
