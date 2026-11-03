# VideoFlow 2.56.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.56.0-linux-x86_64` — SHA-256 `534e3370df36a49f1ad17dbf4a8922e3f1d6972482b869dfebe54d18c284059d`
- `VideoFlow-2.56.0-x86_64.AppImage` — SHA-256 `06604b5eee9bb246554e7869ea19cd070a8a7b3ecbe3b002aecbf85e1632919e`
- `sbom.json` — SHA-256 `267b520f8d9efda0ccfcc352034ebd4e6b2d21580162f5f4edb9fd02d2b90ba0`

## Run

Linux plain binary:

```bash
./videoflow-2.56.0-linux-x86_64 doctor
./videoflow-2.56.0-linux-x86_64 demo -o demo
./videoflow-2.56.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.56.0-x86_64.AppImage
./VideoFlow-2.56.0-x86_64.AppImage version
./VideoFlow-2.56.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
