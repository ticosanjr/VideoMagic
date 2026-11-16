# VideoFlow 2.90.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.90.0-linux-x86_64` — SHA-256 `270f381e722ffcf2d43a85d97d3bf49ceacebc18039c25dff61c18e0974f8595`
- `VideoFlow-2.90.0-x86_64.AppImage` — SHA-256 `c3937a3333d8c18e9943868809b84eba7c3fd4b054bb158f385838b7b67c13b1`
- `VideoFlow-2.90.0-linux-x86_64.tar.zst` — SHA-256 `cce12de23274461f317252de158a5e9b3c59198f5a75d0b740bd57f6809f65fa`
- `VideoFlow-2.90.0-mcp-servers.tar.zst` — SHA-256 `25b63c9d2c0b1ae89e34c89be47b05d05ca6819cd60ffdaa306aed9c3fcb5401`
- `sbom.json` — SHA-256 `66dd768386bf37019dfd0b9f3d6face67b38667971df2edadd8d362f079ab574`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.90.0-mcp-servers.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.90.0-linux-x86_64 doctor
./videoflow-2.90.0-linux-x86_64 recipe list
./videoflow-2.90.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.90.0-x86_64.AppImage
./VideoFlow-2.90.0-x86_64.AppImage version
./VideoFlow-2.90.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
