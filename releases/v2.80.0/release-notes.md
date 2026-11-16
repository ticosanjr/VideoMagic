# VideoFlow 2.80.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.80.0-linux-x86_64` — SHA-256 `1d205934ce8249142a253517e90eaca56ef894dbc484420d7c9a02da65be8866`
- `VideoFlow-2.80.0-x86_64.AppImage` — SHA-256 `7715b51051000a054edbf4d0f220d6543983f74b183b8e7b819fb58701e6177a`
- `VideoFlow-2.80.0-linux-x86_64.tar.zst` — SHA-256 `e9b6a71fa20da4b818e184190b9775d9233729bacac1e1509b52ddc2e087c4b0`
- `sbom.json` — SHA-256 `765d0b196839c50d9e1e7c4e55fc3a31641c8d73071c184696449d34eaf61840`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.80.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.80.0-linux-x86_64 doctor
./videoflow-2.80.0-linux-x86_64 recipe list
./videoflow-2.80.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.80.0-x86_64.AppImage
./VideoFlow-2.80.0-x86_64.AppImage version
./VideoFlow-2.80.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
