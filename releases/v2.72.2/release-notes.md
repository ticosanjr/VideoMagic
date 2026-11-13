# VideoFlow 2.72.2

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.72.2-linux-x86_64` — SHA-256 `1b5d5ea1f3ae832e92dc3653bdb344aab47c532babc6fc613f90a1f3974cca22`
- `VideoFlow-2.72.2-x86_64.AppImage` — SHA-256 `d087b11825500957d65f9856796854ce5dc0ae50602d8bc292436c8486264541`
- `sbom.json` — SHA-256 `647909c6202db1e2055c434bab49240bf32987c3a652183aa3d3421142eb7bf3`

## Run

Linux plain binary:

```bash
./videoflow-2.72.2-linux-x86_64 doctor
./videoflow-2.72.2-linux-x86_64 recipe list
./videoflow-2.72.2-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.72.2-x86_64.AppImage
./VideoFlow-2.72.2-x86_64.AppImage version
./VideoFlow-2.72.2-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
