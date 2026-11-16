# VideoFlow 2.85.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.85.0-linux-x86_64` — SHA-256 `a86b4b002620eba5dd98c1a7051bac13572feb1cd746bf482760b95e9e6834d5`
- `VideoFlow-2.85.0-x86_64.AppImage` — SHA-256 `f889e82952eab698584f33b90b9525ae29325557e336df42eb0340b085c34e71`
- `VideoFlow-2.85.0-linux-x86_64.tar.zst` — SHA-256 `51a08a5c273701a5de1e2600dc1803c776be72323b31d09c13e9a10ccc3416af`
- `sbom.json` — SHA-256 `7321e40ba5160929739ca193857ef9de975331fdb88209084b86b79867d7bcba`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.85.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.85.0-linux-x86_64 doctor
./videoflow-2.85.0-linux-x86_64 recipe list
./videoflow-2.85.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.85.0-x86_64.AppImage
./VideoFlow-2.85.0-x86_64.AppImage version
./VideoFlow-2.85.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
