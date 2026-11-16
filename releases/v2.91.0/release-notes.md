# VideoFlow 2.91.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.91.0-linux-x86_64` — SHA-256 `568df769f43e605b4b759d8118968adbe7afa9b1bc255be9f9cdb934284b3029`
- `VideoFlow-2.91.0-x86_64.AppImage` — SHA-256 `faba831a47f64fea566e6ce40eb8f4fdca5c85d8fadf48fedd662f35739f87c5`
- `VideoFlow-2.91.0-linux-x86_64.tar.zst` — SHA-256 `7eeb0371408fff4d0e93c60e0fdac967aedd0fdd17b92cb4bb74f7b37943cee0`
- `VideoFlow-2.91.0-mcp-servers.tar.zst` — SHA-256 `543f7f059a2835757cd4ecaa0ef29b0f7f12e27ca06b5f9eefd01fef684285a4`
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
