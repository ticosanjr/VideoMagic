# VideoFlow 2.58.6

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.58.6-linux-x86_64` — SHA-256 `f3d1e275bc5f4236d3f8498a95c63c0aee44dcb145b88681d0720d88fd5d7853`
- `VideoFlow-2.58.6-x86_64.AppImage` — SHA-256 `bb84ca15117b670d51a6111bb89e809db22bef784148714d8b36afb000064822`
- `sbom.json` — SHA-256 `28c47713b210699120ccb1e756c39afb4278bafde50e57d50840eae780a9c0e1`

## Run

Linux plain binary:

```bash
./videoflow-2.58.6-linux-x86_64 doctor
./videoflow-2.58.6-linux-x86_64 demo -o demo
./videoflow-2.58.6-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.58.6-x86_64.AppImage
./VideoFlow-2.58.6-x86_64.AppImage version
./VideoFlow-2.58.6-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
