# VideoFlow 2.91.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.91.0-linux-x86_64` — SHA-256 `7ea5059704469511de7dc839e17d8e208787b74d6325e805c43dda447715735f`
- `VideoFlow-2.91.0-x86_64.AppImage` — SHA-256 `a054f32fc84340ed44f5bb9d3d1812317b92fd53f2c274b80683e1967864acdf`
- `VideoFlow-2.91.0-linux-x86_64.tar.zst` — SHA-256 `4ef9ac5ae0f4c591840525e83b2a18a35d33b943804630ccf8e39771f6f2eb80`
- `VideoFlow-2.91.0-mcp-servers.tar.zst` — SHA-256 `29ec81915635b77538aa4224dd3659c7e80b7f5647e6538e6a33c9909e23f74d`
- `sbom.json` — SHA-256 `7b6ce705e088d7479d5bbbb47e197c02603e09bab1afbf9022862dc414b6697e`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.91.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.91.0-linux-x86_64 doctor
./videoflow-2.91.0-linux-x86_64 recipe list
./videoflow-2.91.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.91.0-x86_64.AppImage
./VideoFlow-2.91.0-x86_64.AppImage version
./VideoFlow-2.91.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
