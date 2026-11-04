# VideoFlow 2.58.2

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.58.2-linux-x86_64` — SHA-256 `1134f4c90e72b62e8806b132abe124af681a8f875cfc865b21e507d8355b0cfb`
- `VideoFlow-2.58.2-x86_64.AppImage` — SHA-256 `ed4249fe8f78200f131f0e8c6403e75b880bd6224c261c47a748d1e1f15456e0`
- `sbom.json` — SHA-256 `d127bba7f4ce90bc32cca109b9c88e8fc1acfcfc8394263b19ad605ca769b535`

## Run

Linux plain binary:

```bash
./videoflow-2.58.2-linux-x86_64 doctor
./videoflow-2.58.2-linux-x86_64 demo -o demo
./videoflow-2.58.2-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.58.2-x86_64.AppImage
./VideoFlow-2.58.2-x86_64.AppImage version
./VideoFlow-2.58.2-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
