# VideoFlow 2.80.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.80.0-linux-x86_64` — SHA-256 `cabdd08309d712b36b6dad9bb2cc057aaf6b12419da1437f0631e275f377ca29`
- `VideoFlow-2.80.0-x86_64.AppImage` — SHA-256 `080a95cfa6e3c0e06378c83486db263ac5dd23ba915741bd01dc49800a03fc11`
- `VideoFlow-2.80.0-linux-x86_64.tar.zst` — SHA-256 `5e858e70f677d521a4805a75617695597980393dfe6d214da839f2099cb4ab0a`
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
