# VideoFlow 2.91.4

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.91.4-linux-x86_64` — SHA-256 `1deb62fb2936faf76ee8b08c49dd162c71543cf0afdfcd8d31620138af8ed693`
- `VideoFlow-2.91.4-x86_64.AppImage` — SHA-256 `8084fd444766e03a8dd525a39e29157f114531a5f7e8c52343919211f48bf0bb`
- `VideoFlow-2.91.4-linux-x86_64.tar.zst` — SHA-256 `86eddbc1a1622ed22e3bef9af3de1262c5df706844b588a575776c8375fdcdf9`
- `VideoFlow-2.91.4-mcp-servers.tar.zst` — SHA-256 `d75151479617d733e7a623c9ca391fbca2cc74f580caf202fff0feb8dd0435d4`
- `sbom.json` — SHA-256 `a19761f8c5761de38becc4a4a9497fbcae694d5023d42f2e56e7456c261ccbb5`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.91.4-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.91.4-linux-x86_64 doctor
./videoflow-2.91.4-linux-x86_64 recipe list
./videoflow-2.91.4-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.91.4-x86_64.AppImage
./VideoFlow-2.91.4-x86_64.AppImage version
./VideoFlow-2.91.4-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
