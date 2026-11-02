# VideoFlow 2.31.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.31.0-linux-x86_64` — SHA-256 `135f290b6e1fd09e7f9fd95c91219abd2b4b21decbe3b26f53b8bca5a2ded6db`
- `VideoFlow-2.31.0-x86_64.AppImage` — SHA-256 `95f7336ded6006bb7642df87867375aa9a78ca7d237354d577dd766f721f4b3f`
- `sbom.json` — SHA-256 `1c5e17468296c372e946b3585f77ffdb2300d71cb2887b78d9dde294b8574a46`

## Run

Linux plain binary:

```bash
./videoflow-2.31.0-linux-x86_64 doctor
./videoflow-2.31.0-linux-x86_64 demo -o demo
./videoflow-2.31.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.31.0-x86_64.AppImage
./VideoFlow-2.31.0-x86_64.AppImage version
./VideoFlow-2.31.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
