# VideoFlow 2.80.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.80.0-linux-x86_64` — SHA-256 `c18097b52d3227e21f6a886ea64049f44fa32263f563b5439a6b411aca6ae508`
- `VideoFlow-2.80.0-x86_64.AppImage` — SHA-256 `10bc0a2ba08462427cab44664f67023a4c2297f47eabfe723fa30f2504bf4d5f`
- `VideoFlow-2.80.0-linux-x86_64.tar.zst` — SHA-256 `0816d9911bbb5cd942d5e3d79556166abb9c0a6ecc80175553401eb0a01fc593`
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
