# VideoFlow 2.63.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Dedicated **Produce · Lamera** workspace with phase progress, run selection, gate history, logs, and controls.
- HITL inbox across Lamera runs, with inline video/image previews and direct approvals.
- Canvas group editor for labels, descriptions, colors, and node membership.
- Recipe-filtered job lists and a 225-unit storyboard target for Lamera.
- Fixed a history-pruning race where a late worker finalizer could rewrite a removed job.

## Artifacts

- `videoflow-2.63.0-linux-x86_64` — SHA-256 `75dfd5c108a177be44dbc0cfdb3e8d076a9d22311065cf0da46e392a0674c147`
- `VideoFlow-2.63.0-x86_64.AppImage` — SHA-256 `c6033a54544174c6ba381f2d593f47edb37e2097f370773da8bfb900ce4c0b43`
- `sbom.json` — SHA-256 `492974ca7d50cf8c84db85f52c55a9f809e3275703c487566fcc65f13ccbfd8f`

## Run

Linux plain binary:

```bash
./videoflow-2.63.0-linux-x86_64 doctor
./videoflow-2.63.0-linux-x86_64 recipe list
./videoflow-2.63.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.63.0-x86_64.AppImage
./VideoFlow-2.63.0-x86_64.AppImage version
./VideoFlow-2.63.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
