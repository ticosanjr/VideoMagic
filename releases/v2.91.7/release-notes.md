# VideoFlow 2.91.7

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.91.7-linux-x86_64` — SHA-256 `b40188d34fa6a5f4e724502aba2bd219f65367e7a77b3bb220d91fcaf8763db5`
- `VideoFlow-2.91.7-x86_64.AppImage` — SHA-256 `e40329e0ee5dfda1f8a19248634f4e6de0f27f0bc3945e2925c7d8ccd4f39ffb`
- `VideoFlow-2.91.7-linux-x86_64.tar.zst` — SHA-256 `3257d6816896cc201c0156db8be961dd311a8039ee46006cb6fcbae044874f25`
- `VideoFlow-2.91.7-mcp-servers.tar.zst` — SHA-256 `c79b54f84034f40f31c9627738c8d0411fe57561f7c9e37da00cb2fc1401220c`
- `sbom.json` — SHA-256 `22d93ad442ae26870ee17ffa0591dbb969c09a4efb295047a05d23a54cd99bee`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.91.7-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.91.7-linux-x86_64 doctor
./videoflow-2.91.7-linux-x86_64 recipe list
./videoflow-2.91.7-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.91.7-x86_64.AppImage
./VideoFlow-2.91.7-x86_64.AppImage version
./VideoFlow-2.91.7-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
