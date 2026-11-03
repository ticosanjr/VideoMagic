# VideoFlow 2.46.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.46.0-linux-x86_64` — SHA-256 `fa032a0b9f8cb9e65fa0a54b377456e75429a06b8683cdbd8939f932039b41b9`
- `VideoFlow-2.46.0-x86_64.AppImage` — SHA-256 `eb27b647dce34e942e7e5fdb6ae8eec9bd702f77ba9ef56be69122f98afc8e2b`
- `sbom.json` — SHA-256 `6227e44aa214fada2e22719472332ebe22f738775653b853c87847db76f98b34`

## Run

Linux plain binary:

```bash
./videoflow-2.46.0-linux-x86_64 doctor
./videoflow-2.46.0-linux-x86_64 demo -o demo
./videoflow-2.46.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.46.0-x86_64.AppImage
./VideoFlow-2.46.0-x86_64.AppImage version
./VideoFlow-2.46.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
