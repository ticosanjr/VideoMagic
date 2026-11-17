# VideoFlow 2.91.3

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.91.3-linux-x86_64` — SHA-256 `f07ab5447077811c024070559756867ade29079d961e5031505df1fa82718e04`
- `VideoFlow-2.91.3-x86_64.AppImage` — SHA-256 `3ab7e8412a2243fa116305cdf81d2d869d8f0498dec03c2272a7f8092d7038d5`
- `VideoFlow-2.91.3-linux-x86_64.tar.zst` — SHA-256 `ab243637300fff2709d95fe8b4490b854e27c5783d651dd5881d864f5b33116c`
- `VideoFlow-2.91.3-mcp-servers.tar.zst` — SHA-256 `82fa6842cf03b5fc1c11c9df74cc41b1cc5423e53cb97babdcd26dba2e6d1d42`
- `sbom.json` — SHA-256 `dd8569870ce697d7b5a3506b197adef029dd7b0befa73f3a84f9e8dc2e5d36fb`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.91.3-mcp-servers.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.91.3-linux-x86_64 doctor
./videoflow-2.91.3-linux-x86_64 recipe list
./videoflow-2.91.3-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.91.3-x86_64.AppImage
./VideoFlow-2.91.3-x86_64.AppImage version
./VideoFlow-2.91.3-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
