# VideoFlow 2.61.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Retakes and research step modules are now focused packages with unchanged APIs.
- Minimal notification defaults: HITL, finished jobs, and blockers only.
- Includes the 2.61.0 intelligence, OpusClip, alignment, and crop work.

## Artifacts

- `videoflow-2.61.1-linux-x86_64` — SHA-256 `ef647e2f226cfa23e5a47dda9cc7d6cb5b3c0c6e7e3140998afaaca78a0e9f89`
- `VideoFlow-2.61.1-x86_64.AppImage` — SHA-256 `a10c4fc6488037734a33ce01d1fcc3134149cdc5dfb180ae980e3dc74808fc1d`
- `sbom.json` — SHA-256 `9f06d54a0960f7160c3549447bba1eef03214aea6b1d58e85616b9bba25dae6b`

## Run

Linux plain binary:

```bash
./videoflow-2.61.1-linux-x86_64 doctor
./videoflow-2.61.1-linux-x86_64 recipe list
./videoflow-2.61.1-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.61.1-x86_64.AppImage
./VideoFlow-2.61.1-x86_64.AppImage version
./VideoFlow-2.61.1-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
