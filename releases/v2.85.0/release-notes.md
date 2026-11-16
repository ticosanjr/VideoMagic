# VideoFlow 2.85.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.85.0-linux-x86_64` — SHA-256 `044bb34eed67b064324ac6a890ddc005eceddef42e5b74a952f868388449132e`
- `VideoFlow-2.85.0-x86_64.AppImage` — SHA-256 `8f4233f9b1b0592d0b33e5d647de5601a787ac75a872ea617d62889d72e99632`
- `VideoFlow-2.85.0-linux-x86_64.tar.zst` — SHA-256 `9e6dfafa9932afeaca46d0d78b907c32a92c39580239e041bc53ad3a91aece4b`
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
