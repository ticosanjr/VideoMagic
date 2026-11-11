# VideoFlow 2.61.2

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Faster-Whisper reports transcription progress per segment, and cancellation stops the worker.
- Running jobs renew their lease and persist progress during long steps.
- Duplicate runs for the same source and output are rejected.
- Stale jobs in the UI show as unavailable instead of a backend 404.
- Large Whisper models on CPU now emit a warning.

## Artifacts

- `videoflow-2.61.2-linux-x86_64` — SHA-256 `f4cc57d467acd95bd62ef510adc39a5c78c40798ae7053d0f1f172c888e5a99a`
- `VideoFlow-2.61.2-x86_64.AppImage` — SHA-256 `12c23490e197369123367a2c308acda5eece56d0bea7a213e0d2d35d28191173`
- `sbom.json` — SHA-256 `9fe1fb2a2323ffe4771785fc96e6631450b94ebd14e11a076d7813787fd992de`

## Run

Linux plain binary:

```bash
./videoflow-2.61.2-linux-x86_64 doctor
./videoflow-2.61.2-linux-x86_64 recipe list
./videoflow-2.61.2-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.61.2-x86_64.AppImage
./VideoFlow-2.61.2-x86_64.AppImage version
./VideoFlow-2.61.2-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
