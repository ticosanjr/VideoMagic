# VideoFlow 2.34.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.34.0-linux-x86_64` — SHA-256 `29dd0a9982fe72e512e96c4b4fc9d51e05fc6d582d45848888773974463d68e7`
- `VideoFlow-2.34.0-x86_64.AppImage` — SHA-256 `ba18be64b870035abfe83a38522d238b462f69fbb7ff9f66e606085f937bebcc`
- `sbom.json` — SHA-256 `8d0e511adbe64453f53f441e3eda6fe66e2fe1d3e15e554dee1bc9e2136d5fb9`

## Run

Linux plain binary:

```bash
./videoflow-2.34.0-linux-x86_64 doctor
./videoflow-2.34.0-linux-x86_64 demo -o demo
./videoflow-2.34.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.34.0-x86_64.AppImage
./VideoFlow-2.34.0-x86_64.AppImage version
./VideoFlow-2.34.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
