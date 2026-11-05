# VideoFlow 2.58.4

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.58.4-linux-x86_64` — SHA-256 `ef204d6b1121da05bf540b5d687ecee3c8f2ea8b9557f50d87e071b72c8c0bf5`
- `VideoFlow-2.58.4-x86_64.AppImage` — SHA-256 `421580cc47cc0c4dde2b5ccaeba6eb7c40e5515aba94bb55cf00e4d08609c13d`
- `sbom.json` — SHA-256 `13fc28c93f7520d1584a681050cf56cf35c104f713402bcd4d4636e4b8b02122`

## Run

Linux plain binary:

```bash
./videoflow-2.58.4-linux-x86_64 doctor
./videoflow-2.58.4-linux-x86_64 demo -o demo
./videoflow-2.58.4-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.58.4-x86_64.AppImage
./VideoFlow-2.58.4-x86_64.AppImage version
./VideoFlow-2.58.4-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
