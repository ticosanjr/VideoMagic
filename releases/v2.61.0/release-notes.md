# VideoFlow 2.61.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- OpenCode V2, DeepSeek, and OpenAI-compatible intelligence routing.
- Hybrid LLM virality scoring and LLM social metadata.
- OpusClip-style Shorts, B-roll, and NLE recipes.
- WhisperX/faster-whisper forced alignment and dynamic crop expressions.
- Optional MediaPipe/YOLO face tracking with motion fallback.
- HITL-first notification defaults with configurable levels.

## Artifacts

- `videoflow-2.61.0-linux-x86_64` — SHA-256 `ac5959d0b64113fd0ba3a81e64b1e5c318fc4b2281f357336dbdc73cf94c5931`
- `VideoFlow-2.61.0-x86_64.AppImage` — SHA-256 `45463a58e007845b933bb8241c9f264707b778e21da9331974d293cdb8064f37`
- `sbom.json` — SHA-256 `71545fb791c4477f686e93e3655c30ba822690070981df1d16ea4d133c62b1d5`

## Run

Linux plain binary:

```bash
./videoflow-2.61.0-linux-x86_64 doctor
./videoflow-2.61.0-linux-x86_64 recipe list
./videoflow-2.61.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.61.0-x86_64.AppImage
./VideoFlow-2.61.0-x86_64.AppImage version
./VideoFlow-2.61.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
