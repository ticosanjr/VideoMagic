# VideoFlow 2.36.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.36.0-linux-x86_64` — SHA-256 `fd5d1ffff737244bf0b46cffd44b7e9b8fab04e09a4e6d0888b617d306041ea8`
- `VideoFlow-2.36.0-x86_64.AppImage` — SHA-256 `d6f4bd896a50d435a532e121585cc50b0039b144d8d1a74bb7716b3cc2af6135`
- `sbom.json` — SHA-256 `b855ef1923a642d49a77853ffd8b8efb7fb43096cae363463c6ac1c8f8a0b5a8`

## Run

Linux plain binary:

```bash
./videoflow-2.36.0-linux-x86_64 doctor
./videoflow-2.36.0-linux-x86_64 demo -o demo
./videoflow-2.36.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.36.0-x86_64.AppImage
./VideoFlow-2.36.0-x86_64.AppImage version
./VideoFlow-2.36.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
