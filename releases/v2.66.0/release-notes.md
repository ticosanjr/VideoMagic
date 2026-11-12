# VideoFlow 2.66.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Eye-contact detection prefers MediaPipe Face Mesh and falls back to OpenCV or the manual audit.
- Independent research agents run concurrently from 2.65.0.
- Partial transcription resume, richer entities, style-guided audio, and expired-license blockers remain included.

## Artifacts

- `videoflow-2.66.0-linux-x86_64` — SHA-256 `f025410a45bc60f39ffb3ee4b2cac995fa61c01728fec19634f3323a6ce603dc`
- `VideoFlow-2.66.0-x86_64.AppImage` — SHA-256 `12b30c05063da2dd1ee482ab77117496e36c400f399ea2f092ce81f97d868691`
- `sbom.json` — SHA-256 `87a8f71c855458b04d7bbfa8374f5c257cdffaee527a4f6729360e7f793e04a4`

## Run

Linux plain binary:

```bash
./videoflow-2.66.0-linux-x86_64 doctor
./videoflow-2.66.0-linux-x86_64 recipe list
./videoflow-2.66.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.66.0-x86_64.AppImage
./VideoFlow-2.66.0-x86_64.AppImage version
./VideoFlow-2.66.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
