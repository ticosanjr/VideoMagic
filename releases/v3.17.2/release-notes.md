# VideoFlow 3.17.2

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `VideoFlow-3.17.2-linux-x86_64.tar.zst` — SHA-256 `3ec8cd6de5eab6932a88083c003eac9fa1d7bab74c64a14e0029403b1945cc90`
- `VideoFlow-3.17.2-x86_64.AppImage` — SHA-256 `23b3b5b294b2e6c4b374546d5c9a5e4cd63b6db743a1d62b13c77ce2cca32f2f`
- `sbom.json` — SHA-256 `6d1b21cbd006bbd512d33af6c3e035afef0fe54350a90200b1aefb3bb85eb81f`
- `VideoFlow-Windows-GPU-Worker-3.17.2.zip` — SHA-256 `ac1ea7470563b797a87114f05fe1213307de67dd8525e784224f6367dda33a7a`
- `VideoFlow-Windows-GPU-Worker-3.17.2.zip.sha256` — SHA-256 `9ffc73d84362e8e0d7057aff6a0044f04e28302123bad31749e1e201f037f350`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.17.2-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.17.2-x86_64.AppImage
./VideoFlow-3.17.2-x86_64.AppImage version
./VideoFlow-3.17.2-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
