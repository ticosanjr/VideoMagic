# VideoFlow 2.58.9

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.58.9-linux-x86_64` — SHA-256 `5c2d4c9f231d63be4a40a392583eb9b416ce978762017509a94832cbeab09b5c`
- `VideoFlow-2.58.9-x86_64.AppImage` — SHA-256 `c3a9be91743d3a17e6acb8c443d442aede048629fb6debfe4cc71783e8a68379`
- `sbom.json` — SHA-256 `0fc4af29068f65d2fcce2410b7300467d6a1a0e68d7bc875e46f641226d2800e`

## Run

Linux plain binary:

```bash
./videoflow-2.58.9-linux-x86_64 doctor
./videoflow-2.58.9-linux-x86_64 demo -o demo
./videoflow-2.58.9-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.58.9-x86_64.AppImage
./VideoFlow-2.58.9-x86_64.AppImage version
./VideoFlow-2.58.9-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
