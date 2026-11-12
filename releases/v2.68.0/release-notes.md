# VideoFlow 2.68.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Optional ElevenLabs voice cloning, disabled by default and gated by consent plus reference samples.
- New `voice.clone` repair step; `voice.patch` prefers a human WAV, then the clone MP3, then TTS.
- Lamera now has 66 nodes and accepts a clone profile id in the fact-check gate.
- MediaPipe/YOLO/OpenCV eye-contact, concurrent research agents, and partial transcription resume remain included.

## Artifacts

- `videoflow-2.68.0-linux-x86_64` — SHA-256 `f1a61448eb8faccab5d5f9c7124d7d2cf3b80aea2712e90df1a8531cab3d0a02`
- `VideoFlow-2.68.0-x86_64.AppImage` — SHA-256 `79150d4dc26eb0ff8763a6a627ff277c65338a25b0b92c9d451b5e9d3d8a8f83`
- `sbom.json` — SHA-256 `9b2631e354d9a3188442b362af32bb16592cf86be4c815834c12e94bbcb659f9`

## Run

Linux plain binary:

```bash
./videoflow-2.68.0-linux-x86_64 doctor
./videoflow-2.68.0-linux-x86_64 recipe list
./videoflow-2.68.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.68.0-x86_64.AppImage
./VideoFlow-2.68.0-x86_64.AppImage version
./VideoFlow-2.68.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
