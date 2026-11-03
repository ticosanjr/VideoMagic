# VideoFlow 2.47.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.47.0-linux-x86_64` — SHA-256 `78946dad8ef7fc2f788d80a0e357663902e96d37332a34dc5db3bbd65599dcb0`
- `VideoFlow-2.47.0-x86_64.AppImage` — SHA-256 `7daed0e8da907611b368b5586a5f7cf13fe37a935e273e293fa363bd3ceb183a`
- `sbom.json` — SHA-256 `76f4a65fe3372b0de8729556132135207c5f7b6bca9edc50c63b01f9b5bef554`

## Run

Linux plain binary:

```bash
./videoflow-2.47.0-linux-x86_64 doctor
./videoflow-2.47.0-linux-x86_64 demo -o demo
./videoflow-2.47.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.47.0-x86_64.AppImage
./VideoFlow-2.47.0-x86_64.AppImage version
./VideoFlow-2.47.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
