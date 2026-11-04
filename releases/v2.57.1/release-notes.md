# VideoFlow 2.57.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.57.1-linux-x86_64` — SHA-256 `c7994c4a2a27cde1cbdafb961907b84a3ec3a484811a9af12c5f9dbede2ade4c`
- `VideoFlow-2.57.1-x86_64.AppImage` — SHA-256 `dabf86f4dbf25c4bc18d8e0c765be67e4705fd6648b24ad21c03ff441994e316`
- `sbom.json` — SHA-256 `4dae9fb66c90e5aa8588a23d6ac99f35bf5e778c9cdcd5dfc5407974099993a7`

## Run

Linux plain binary:

```bash
./videoflow-2.57.1-linux-x86_64 doctor
./videoflow-2.57.1-linux-x86_64 demo -o demo
./videoflow-2.57.1-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.57.1-x86_64.AppImage
./VideoFlow-2.57.1-x86_64.AppImage version
./VideoFlow-2.57.1-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
