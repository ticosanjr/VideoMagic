# VideoFlow 4.0.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `VideoFlow-4.0.0-x86_64.AppImage` — SHA-256 `bc5ddc408935eb5be26f57c5ce3af8d61fe956b93210e5db0153e308a49cefa3`
- `VideoFlow-4.0.0-linux-x86_64.tar.zst` — SHA-256 `a7c1c21913a41f54cbb00cff36c460e34d68d70c50be636d50b2fe1eb6731cfc`
- `VideoFlow-Windows-GPU-Worker-4.0.0.zip` — SHA-256 `3938ecdb95cef9843d39ebefb656c40f71a2f40e33f6764411c10b0f6475d66f`
- `VideoFlow-Windows-GPU-Worker-4.0.0.zip.sha256` — SHA-256 `b7604618e2f39716945e1a9dde4f790781b58ee3aa70567852f9a1eac1249e13`
- `sbom.json` — SHA-256 `a4fe3b57b7e68525143e7ab36722c62bed1eb65b8362dbe3254e975dafee815e`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-4.0.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-4.0.0-x86_64.AppImage
./VideoFlow-4.0.0-x86_64.AppImage version
./VideoFlow-4.0.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
