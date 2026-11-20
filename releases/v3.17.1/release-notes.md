# VideoFlow 3.17.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `VideoFlow-3.17.1-linux-x86_64.tar.zst` — SHA-256 `be520ec50238a2406bdc412af04f6dcb03e1ab271cda7abeae72d26f25cf1cb4`
- `VideoFlow-3.17.1-x86_64.AppImage` — SHA-256 `37ccf38c32ea82347b9df0b96fd550c3b5dae4514a5ec5aaf9c9305e41331c05`
- `sbom.json` — SHA-256 `b0054cb62d9528bfaf512b21a99972330f62d1a82af337258a7d3a992ae42ade`
- `VideoFlow-Windows-GPU-Worker-3.17.1.zip` — SHA-256 `e59fd0c9de0e4929d16f9f10e8f881fb6459a6728e6b52360549dad9395a1118`
- `VideoFlow-Windows-GPU-Worker-3.17.1.zip.sha256` — SHA-256 `3beccf5a2b9a986ebf1fcd62703525432630dd7b8e6a278fda70d1e9f25b1c44`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.17.1-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.17.1-x86_64.AppImage
./VideoFlow-3.17.1-x86_64.AppImage version
./VideoFlow-3.17.1-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
