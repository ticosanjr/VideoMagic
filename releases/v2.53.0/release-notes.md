# VideoFlow 2.53.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.53.0-linux-x86_64` — SHA-256 `90bb1f6d34749f0b78e8140c071adb12f246f4679e8b2734c4ed5b798ef61ae1`
- `VideoFlow-2.53.0-x86_64.AppImage` — SHA-256 `11f999354c8623a8eaea0261c3529ccc0e1fcde4d1e9adc370ecdc0cd9e777db`
- `sbom.json` — SHA-256 `41aeaf9b8c086b1f8a114a5de2f1f0677b0b5ce754a24a588be1b82cf8bd0c26`

## Run

Linux plain binary:

```bash
./videoflow-2.53.0-linux-x86_64 doctor
./videoflow-2.53.0-linux-x86_64 demo -o demo
./videoflow-2.53.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.53.0-x86_64.AppImage
./VideoFlow-2.53.0-x86_64.AppImage version
./VideoFlow-2.53.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
