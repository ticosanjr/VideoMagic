# VideoFlow 2.25.3

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.25.3-linux-x86_64` — SHA-256 `e0307a51005b70a79fbc7df87e84be1740356ed0d85c75fbd5202da136502d0a`
- `VideoFlow-2.25.3-x86_64.AppImage` — SHA-256 `2460264a06be74a92e95626a2da049b2355df6eee7edbd5bbc867fd7c863700e`
- `sbom.json` — SHA-256 `152fc5482ce05cf0f512ae75f70e8834fb993c289a2ef136f6be83bbcdd86948`

## Run

Linux plain binary:

```bash
./videoflow-2.25.3-linux-x86_64 doctor
./videoflow-2.25.3-linux-x86_64 demo -o demo
./videoflow-2.25.3-linux-x86_64 run input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.25.3-x86_64.AppImage
./VideoFlow-2.25.3-x86_64.AppImage version
./VideoFlow-2.25.3-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
