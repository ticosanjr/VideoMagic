# VideoFlow 2.32.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.32.0-linux-x86_64` — SHA-256 `ad23271c7317ce0301dbbe2dcd0e0ae796af89700cf36629a29194a379e07558`
- `VideoFlow-2.32.0-x86_64.AppImage` — SHA-256 `802046ed7268e870f0846436705f27fbe16a6c12a5b0ae748e8aa00ce3bb5e20`
- `sbom.json` — SHA-256 `cd6929f4c6893e85931cbcfec0b6102b36fe56dc676f6126f8bdaf8694b46e65`

## Run

Linux plain binary:

```bash
./videoflow-2.32.0-linux-x86_64 doctor
./videoflow-2.32.0-linux-x86_64 demo -o demo
./videoflow-2.32.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.32.0-x86_64.AppImage
./VideoFlow-2.32.0-x86_64.AppImage version
./VideoFlow-2.32.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
