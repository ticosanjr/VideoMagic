# VideoFlow 2.72.4

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.72.4-linux-x86_64` — SHA-256 `20064f6b0a8d4a86670bf24b169cba14278e75f4f2db1f49a14268d0dfc078ce`
- `VideoFlow-2.72.4-x86_64.AppImage` — SHA-256 `e0e201106c49838299f3b682a995dce2afac2aebb50eb8b33ee10488a143dd38`
- `VideoFlow-2.72.4-linux-x86_64.tar.zst` — SHA-256 `cf7bc73dd2d10e3fa09e0f0898036f0b126e9924ad4c2fed448215a45d8c5eb3`
- `sbom.json` — SHA-256 `af0f08b4d321bcc82be3cacc32a684a3b97b9e53b3457168a2503542345c887d`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.72.4-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.72.4-linux-x86_64 doctor
./videoflow-2.72.4-linux-x86_64 recipe list
./videoflow-2.72.4-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.72.4-x86_64.AppImage
./VideoFlow-2.72.4-x86_64.AppImage version
./VideoFlow-2.72.4-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
