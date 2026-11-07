# VideoFlow 2.59.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.59.0-linux-x86_64` — SHA-256 `8d7c688736fb06bae6c02cdf5f0908bfa5ef62b2d757c7a30b1d27ce67eed506`
- `VideoFlow-2.59.0-x86_64.AppImage` — SHA-256 `97e01ae350fcb5d4cfef8ddb04d401d9355999eaf7211b8caaba6770192e071d`
- `sbom.json` — SHA-256 `7d7e4c2a69da29fc09c309a9330f47cc5a5abd1f612857fca6c30cb6f10c56ae`

## Run

Linux plain binary:

```bash
./videoflow-2.59.0-linux-x86_64 doctor
./videoflow-2.59.0-linux-x86_64 demo -o demo
./videoflow-2.59.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.59.0-x86_64.AppImage
./VideoFlow-2.59.0-x86_64.AppImage version
./VideoFlow-2.59.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
