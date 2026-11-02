# VideoFlow 2.29.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.29.0-linux-x86_64` — SHA-256 `8a332bca0766d6d433af41c127d94ed985a200b7dcad6da974f6163b74a96a6a`
- `VideoFlow-2.29.0-x86_64.AppImage` — SHA-256 `f9d4ac6faeea6eb02a89a11007b3990f9da8c37f96575a336dea39edf460d03e`
- `sbom.json` — SHA-256 `ccc67cfc581b95b10760b99ef1711ab0c23e86d0e28fed16f579c12dbcd676d2`

## Run

Linux plain binary:

```bash
./videoflow-2.29.0-linux-x86_64 doctor
./videoflow-2.29.0-linux-x86_64 demo -o demo
./videoflow-2.29.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.29.0-x86_64.AppImage
./VideoFlow-2.29.0-x86_64.AppImage version
./VideoFlow-2.29.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
