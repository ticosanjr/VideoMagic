# VideoFlow 2.33.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.33.1-linux-x86_64` — SHA-256 `f8c75d8862c124533cbbc46372568b1d412f7f2b6ff91abdff27dcfac1f65c01`
- `VideoFlow-2.33.1-x86_64.AppImage` — SHA-256 `14883571b63f10381a0625d6f106cf6d69cc0e74154d5fb0c06e78194d4bb6b1`
- `sbom.json` — SHA-256 `6ce07021f6e0f63f0cf4e776fc6115e88e604c467c806bc77cd1babce60dc46e`

## Run

Linux plain binary:

```bash
./videoflow-2.33.1-linux-x86_64 doctor
./videoflow-2.33.1-linux-x86_64 demo -o demo
./videoflow-2.33.1-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.33.1-x86_64.AppImage
./VideoFlow-2.33.1-x86_64.AppImage version
./VideoFlow-2.33.1-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
