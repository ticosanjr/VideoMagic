# VideoFlow 2.91.8

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.91.8-linux-x86_64` — SHA-256 `8b2ed5c0f79a51390fd15a8644fbdec8fd09b4d3ab4f27b949612af07b654a58`
- `VideoFlow-2.91.8-x86_64.AppImage` — SHA-256 `41192ee3d524900409a8a65af1782e6779f198cb778a40d831ad34e0a534976a`
- `VideoFlow-2.91.8-linux-x86_64.tar.zst` — SHA-256 `7de115b10dcf63cc363004c6b9a34737c6fc9491f60eac31726477e1b5e3af02`
- `VideoFlow-2.91.8-mcp-servers.tar.zst` — SHA-256 `0e8cc79e352630c9411aa6906f05812634be5f04637d66b5f694af42ae5d9428`
- `sbom.json` — SHA-256 `8d28bc703da838bb921a6ab2ff1dde5c292410f352c47862e93fe62ac4093bb6`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.91.8-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.91.8-linux-x86_64 doctor
./videoflow-2.91.8-linux-x86_64 recipe list
./videoflow-2.91.8-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.91.8-x86_64.AppImage
./VideoFlow-2.91.8-x86_64.AppImage version
./VideoFlow-2.91.8-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
