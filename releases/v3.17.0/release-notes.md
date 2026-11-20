# VideoFlow 3.17.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `VideoFlow-3.17.0-linux-x86_64.tar.zst` — SHA-256 `cb1cdfc6923ec4c02cacff39285eb2f1b72543e263542d191c308b8f0bdbb20a`
- `VideoFlow-3.17.0-x86_64.AppImage` — SHA-256 `08f5386d397c44d7a9732b0bed31d816c1e1cc79415f9e5d924668f58220783b`
- `sbom.json` — SHA-256 `f1b3dab97fd30dd843ff7367797dc127281c8b4b7dbb8ad526780b9dfb601cc9`
- `VideoFlow-Windows-GPU-Worker-3.17.0.zip` — SHA-256 `ce3ae976c29d4317d02ae22d8351736c20797901d1828efa2f08808be0f93b29`
- `VideoFlow-Windows-GPU-Worker-3.17.0.zip.sha256` — SHA-256 `a7dccb6b00fa06e54dc593429d839c32444fadfeeaef2bec20f073880a0b719c`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.17.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.17.0-x86_64.AppImage
./VideoFlow-3.17.0-x86_64.AppImage version
./VideoFlow-3.17.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
