# VideoFlow 2.91.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.91.1-linux-x86_64` — SHA-256 `9bbe313b4e68c7a7963ecfa4e0086c9d529a7937c8b89ae96fc46aa9ee2a3c7b`
- `VideoFlow-2.91.1-x86_64.AppImage` — SHA-256 `ec46e174289811a99839b921e5793357df892270d0dc6ededfb929fc6c80ebc8`
- `VideoFlow-2.91.1-linux-x86_64.tar.zst` — SHA-256 `3020846287733a38b49be13bb1a3dd03cfa1266c2f31097fa3705be2c6623faa`
- `VideoFlow-2.91.1-mcp-servers.tar.zst` — SHA-256 `5b09b6f247d89bcc55b74e4efd8e605244e960539430a498b38cd65b93c045d0`
- `sbom.json` — SHA-256 `532ba961337bb880279bfc4cfb2f71b27f97b9a220648f12ceca6f35b19c0d20`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.91.1-mcp-servers.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.91.1-linux-x86_64 doctor
./videoflow-2.91.1-linux-x86_64 recipe list
./videoflow-2.91.1-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.91.1-x86_64.AppImage
./VideoFlow-2.91.1-x86_64.AppImage version
./VideoFlow-2.91.1-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
