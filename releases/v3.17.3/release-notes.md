# VideoFlow 3.17.3

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `VideoFlow-3.17.3-linux-x86_64.tar.zst` — SHA-256 `e5a7126d3850c9bf91815a7fa6cdce401c4de40497dd0c4b618f6eaf51284245`
- `VideoFlow-3.17.3-x86_64.AppImage` — SHA-256 `1df4e81aab134875211492089aa3200bd32afb5d7fb6f48c50df3468119ed196`
- `VideoFlow-Windows-GPU-Worker-3.17.3.zip` — SHA-256 `444968a9c1c0b82d620ed04ace49ef5d4164339201a7338c0e6ecbf936aa28d7`
- `VideoFlow-Windows-GPU-Worker-3.17.3.zip.sha256` — SHA-256 `0e317447123662d0cbc66a5f7136a6c6b8c2876cdbd338564ef12e8e193c93f9`
- `sbom.json` — SHA-256 `96026cf46fae81195bcb5fccb18f1ccf9c32fee3814e30c4e60efcb29de06689`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.17.3-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.17.3-x86_64.AppImage
./VideoFlow-3.17.3-x86_64.AppImage version
./VideoFlow-3.17.3-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
