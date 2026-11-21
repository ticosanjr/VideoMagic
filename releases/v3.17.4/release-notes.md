# VideoFlow 3.17.4

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `VideoFlow-3.17.4-linux-x86_64.tar.zst` — SHA-256 `4cc7e8db7d76bbc6695cbcfb14c0c1f5b05dcc306d84c611132ec8648793893c`
- `VideoFlow-3.17.4-x86_64.AppImage` — SHA-256 `ac8ddbd0385912f69cc9022e6db3fc34a8507b2a25440a68cbc9f1ef60e0f43b`
- `VideoFlow-Windows-GPU-Worker-3.17.4.zip` — SHA-256 `3326734b77207880ce24df3f343fcdec542e16bbf38e4e897431153f358e90ce`
- `VideoFlow-Windows-GPU-Worker-3.17.4.zip.sha256` — SHA-256 `1d7c2914017de4b81ddc1f1a05605141e8aa1ac1ca334daf36a1d161171cbbea`
- `sbom.json` — SHA-256 `9e02faa398ed35387c4734596323fa38e0a1ad0dea9f7439aec2fa02d70f0b43`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.17.4-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.17.4-x86_64.AppImage
./VideoFlow-3.17.4-x86_64.AppImage version
./VideoFlow-3.17.4-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
