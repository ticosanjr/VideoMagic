# VideoFlow 2.40.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.40.0-linux-x86_64` — SHA-256 `dc8aefc1c8e4f7724689ab954093be1c3e939cc00d66579d6456efb86211ab6f`
- `VideoFlow-2.40.0-x86_64.AppImage` — SHA-256 `27320971f8f7c0b7d1ce0e94593e7b9d987e8a833bc950e9047ba2f32622843b`
- `sbom.json` — SHA-256 `b4d4d7515d165b7b269bff1f5a6eb15eb11ec304f737d273e08314e70e3f4a5d`

## Run

Linux plain binary:

```bash
./videoflow-2.40.0-linux-x86_64 doctor
./videoflow-2.40.0-linux-x86_64 demo -o demo
./videoflow-2.40.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.40.0-x86_64.AppImage
./VideoFlow-2.40.0-x86_64.AppImage version
./VideoFlow-2.40.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
