# VideoFlow 2.58.7

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.58.7-linux-x86_64` — SHA-256 `96599c59a6e9cf89aa8ffaeb45ee17f05e2d2a51c09365823da643e67313c74d`
- `VideoFlow-2.58.7-x86_64.AppImage` — SHA-256 `b5fdefc34a1ed62e1b404319a8f3f4a6c182c37d84b45a49723a6d88ddcc92d1`
- `sbom.json` — SHA-256 `f06d433a607333c83f101f91c916b3aff4c7f30cfa6b7b17fcb2bb40a7d51adf`

## Run

Linux plain binary:

```bash
./videoflow-2.58.7-linux-x86_64 doctor
./videoflow-2.58.7-linux-x86_64 demo -o demo
./videoflow-2.58.7-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.58.7-x86_64.AppImage
./VideoFlow-2.58.7-x86_64.AppImage version
./VideoFlow-2.58.7-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
