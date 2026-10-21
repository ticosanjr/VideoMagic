# VideoFlow 0.22.0

Portable video pre-edit pipeline with a lean, downloadable-model build.

This release keeps the portable artifacts small by excluding speech model
weights. whisper.cpp and Faster-Whisper runtimes are included; download the
small Faster-Whisper model (484 MB) or whisper.cpp tiny model (75 MB) from the
Models tab, or point `VIDEOWFLOW_FASTER_WHISPER_MODEL` / `VIDEOWFLOW_WHISPER_MODEL`
at a local model.

## Highlights

- Studio tab with AI Analysis, Timeline, Keyframes, Tracks, and Transitions.
- OpenAI-compatible multimodal Short analysis via API and MCP.
- LLM emoji captions that re-render one Short.
- On-demand model downloads with SHA-256 verification and removal.
- 30 transcription language codes, including auto-detect.
- 1080/1440/2160 short-edge renders (4K vertical, square, or landscape).
- Forty-one MCP tools and four resources.

## Artifacts

- `videoflow-0.22.0-linux-x86_64` — SHA-256 `be7f9dbde6c7a09dde14a33e850025d069a2c9a76df7e8ac4937599f1ea01c65`
- `VideoFlow-0.22.0-x86_64.AppImage` — SHA-256 `43681b92ba451e9f0e3db6906711178ead078f31f57a7fa461bfb84a220a8175`

## Run

Linux plain binary:

```bash
chmod +x videoflow-0.22.0-linux-x86_64
./videoflow-0.22.0-linux-x86_64 doctor
./videoflow-0.22.0-linux-x86_64 serve   # API + MCP HTTP + rack UI
./videoflow-0.22.0-linux-x86_64 run input.mp4 -o project --transcribe
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-0.22.0-x86_64.AppImage
./VideoFlow-0.22.0-x86_64.AppImage version
./VideoFlow-0.22.0-x86_64.AppImage serve
```

Open the Models tab and download a speech model before the first transcription.
External vision or emoji generation also requires enabling external services and
configuring an OpenAI-compatible endpoint.

## Notes

Windows PE is not included in this release because the Windows/Wine build host
was unavailable. See `CHANGELOG.md` for the full change list.
