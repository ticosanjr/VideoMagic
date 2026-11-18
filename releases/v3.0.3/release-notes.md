# VideoFlow 3.0.3

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-3.0.3-linux-x86_64` — SHA-256 `6dc1fa0126e90f8ee698625633b314dcfcb7d3788bb2f5c68fae7c6436605834`
- `VideoFlow-3.0.3-x86_64.AppImage` — SHA-256 `32ad4d88dc0fa4bfd8e2b7dfd8c71688ca280f6d7276c914941a827cda46c61f`
- `VideoFlow-3.0.3-linux-x86_64.tar.zst` — SHA-256 `71718bbdcc532a85cdeae58ea4d685d7fa98303289436078f37654a61e4baf9d`
- `VideoFlow-3.0.3-mcp-servers.tar.zst` — SHA-256 `f421424d397c210e7be8a27f68da9210ea4edaa8282e1a2336d6b21ce95232f6`
- `sbom.json` — SHA-256 `5a0ab5446084b905dffec15fd70720fafae9e45333b91670da0f5c1e967aa093`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.0.3-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-3.0.3-linux-x86_64 doctor
./videoflow-3.0.3-linux-x86_64 recipe list
./videoflow-3.0.3-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.0.3-x86_64.AppImage
./VideoFlow-3.0.3-x86_64.AppImage version
./VideoFlow-3.0.3-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
