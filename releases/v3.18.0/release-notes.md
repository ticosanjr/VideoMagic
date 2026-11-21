# VideoFlow 3.18.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `VideoFlow-3.18.0-linux-x86_64.tar.zst` — SHA-256 `b89e8e21807050cb6fe4b9c71fe8ecd8b134e6f4d65895a90ed07ef2b40cca81`
- `VideoFlow-3.18.0-x86_64.AppImage` — SHA-256 `f8a4a54cb8cad37329b70bd227612f1443a00cdc9e8a06e8dc21d914a0cd9fad`
- `VideoFlow-Windows-GPU-Worker-3.18.0.zip` — SHA-256 `de9663b6ad95016bebe52cf364db1fa583bb2b0270fd901c7f2748302d7cab01`
- `VideoFlow-Windows-GPU-Worker-3.18.0.zip.sha256` — SHA-256 `0a15d5b1edc90246d73d8a252494a455d8beeebb6828c68b06aaed1fc8db27bf`
- `sbom.json` — SHA-256 `2bbdd6475712f6cad824c174620ceebd90967b4ae88acc6930bf0f44d5a97ffa`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.18.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.18.0-x86_64.AppImage
./VideoFlow-3.18.0-x86_64.AppImage version
./VideoFlow-3.18.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
