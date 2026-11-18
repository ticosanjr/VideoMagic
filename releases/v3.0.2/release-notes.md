# VideoFlow 3.0.2

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-3.0.2-linux-x86_64` — SHA-256 `540b0a1ff8d3497f6b98423b6a6118087c54bd9adaa0315e30fccef76c66d946`
- `VideoFlow-3.0.2-x86_64.AppImage` — SHA-256 `ad65dab9541420bf718072fc104b9d57c8b2ef375a9fd745e9a4113bb0e955ff`
- `VideoFlow-3.0.2-linux-x86_64.tar.zst` — SHA-256 `89b3e1aeb58a49bc58fc560018711aef1d7a55d37fe314e1c5fe827d95ab52a1`
- `VideoFlow-3.0.2-mcp-servers.tar.zst` — SHA-256 `8e06a1964021364b5b8bd45c88daac26fbd9c6651ec6e64dc2dab56b94b4ca4b`
- `sbom.json` — SHA-256 `fac9c5e5d5b2d0d1ced1f3c76aa012b2dac6e8525230a51c9bbe4cd4a7ad8244`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.0.2-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-3.0.2-linux-x86_64 doctor
./videoflow-3.0.2-linux-x86_64 recipe list
./videoflow-3.0.2-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.0.2-x86_64.AppImage
./VideoFlow-3.0.2-x86_64.AppImage version
./VideoFlow-3.0.2-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
