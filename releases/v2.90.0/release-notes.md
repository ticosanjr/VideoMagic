# VideoFlow 2.90.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.90.0-linux-x86_64` — SHA-256 `e022f3a36add474e7691681a1765c027df0e40d2eeefdd685e9dbc7449b1ae6b`
- `VideoFlow-2.90.0-x86_64.AppImage` — SHA-256 `714793330e3256d511e6d9b5947a385f0b3f4fb7fde51d8bd3e2bf8ffb1eb358`
- `VideoFlow-2.90.0-linux-x86_64.tar.zst` — SHA-256 `90559cec3280463840d070a82324b2ee95a242466b16d32b770843946760c193`
- `VideoFlow-2.90.0-mcp-servers.tar.zst` — SHA-256 `38e16a52d08a8cd01340456f3c9b1dcd186c49ef781fe5e30d949214560c6aa9`
- `sbom.json` — SHA-256 `e18d87bf7c27d46ca5b8c9fbbad98cb481f7fabcf1c0b6767f960dbe2ffd45b3`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.90.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.90.0-linux-x86_64 doctor
./videoflow-2.90.0-linux-x86_64 recipe list
./videoflow-2.90.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.90.0-x86_64.AppImage
./VideoFlow-2.90.0-x86_64.AppImage version
./VideoFlow-2.90.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
